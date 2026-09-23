/**
 * jev-pilot: phase discipline for a cheap model, with Jev where it measures something.
 *
 * goal       the agent reads goal-comprehension.md and the ground, then drafts the goal with
 *            pilot_set_goal. Jev scores each open question by blast radius: high goes to the
 *            user, low the agent decides. The USER agrees; Jev only sorts their reply into
 *            confirm, amend, reject, or other.
 * solution   the agent reads solution-confidence.md, consults an oracle, then pilot_propose.
 *            Jev scores the approach per criterion as a warning, never a block.
 * execution  stuck detection in code.
 * review     any stop that is not a question for the user sends the agent to verify each
 *            criterion (review-verification.md advised) and cite the tool output per criterion
 *            with pilot_report; code checks each citation is verbatim tool output.
 * completion Jev checks each criterion against its own citations plus the final message.
 *            Hard gate; a release after three blocks is told to the agent and the user.
 *
 * Blocks: edits until the goal is agreed and an approach proposed; pilot_set_goal until
 * goal-comprehension.md was read, pilot_propose until solution-confidence.md was read (once per
 * activation); "finished" during the solution phase is sent back to propose (twice at most).
 * Criteria tagged `process` (how the work is done or reported) are left out of the approach
 * check, which a plan cannot show; completion checks every criterion.
 * UI: one chip in the status bar carries Jev's latest result; popups only when something fails.
 */

import { existsSync, realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { ExtensionAPI, ExtensionContext } from "@oh-my-pi/pi-coding-agent";
import { TypeSafeClient, type Questions, type SystemOneResult } from "@typesafe-ai/sdk";

// Built on /pilot from the harness's own credential store (agent.db `auth_credentials`, via the
// model registry), so the key omp already uses for `judge` is the key the pilot uses.
let jevClient: TypeSafeClient | null = null;

/**
 * A client for the registry's TypeSafe judge model, or the reason there is none. `ctx.models` lists
 * chat models only, so judge-kind models come from the registry's full pool.
 */
async function connectJev(ctx: ExtensionContext): Promise<TypeSafeClient | string> {
  const models = ctx.modelRegistry.getAvailable("all").filter((m) => m.api === "typesafe");
  const model = models.find((m) => m.id === "jev-latest") ?? models[0];
  if (!model) return "no TypeSafe judge model is available; run /login typesafe";
  const apiKey = await ctx.modelRegistry.getApiKey(model);
  if (!apiKey) return `no credential for provider "${model.provider}"; run /login typesafe`;
  return new TypeSafeClient({ apiKey, baseURL: model.baseUrl, defaultModel: model.id });
}

const ICON = {
  goal: "🎯", solution: "💡", execution: "⚡", review: "🔍", completion: "🏁",
  blocked: "🚫", stuck: "🔄", done: "✅", inactive: "",
} as const;

type Phase = "inactive" | "goal" | "solution" | "execution" | "review" | "completion";
type Criterion = { label: string; criterion: string; kind: "product" | "process" };
type PilotMessage = { customType: string; content: string };
const MAX_REDIRECTS = 2;        // "finished" before a proposal: sent back this many times, then let through

const PASS = 0.5;               // per-criterion bar: warning at solution, gate at completion
const STRUCTURE_WARN = 0.5;     // P(waste = structure) above this: the agent tells the user the approach is high-stakes
// P(structure) at or above this sends a question to the user. goal-comprehension.md measured four
// cases: 0.07 (a word), 0.28 (genuinely ambiguous), 0.35 ("make it faster" as latency), 0.44 (an
// architecture). Only the first is safe to decide alone. Provisional: four points, not a calibration.
const ASK_USER_AT = 0.25;
const MAX_BLOCKS = 3;           // completion blocks before releasing, unverified
const RECORD_CHARS = 20000;     // per tool result kept for checking cited evidence
const CITE_CHARS = 2000;        // per cited excerpt

// Relative to the file's real location (installs may symlink it): the skill sits at
// ../../.agents/skills beside agent/extensions, in ~/.omp and in agent-kit alike.
const REF = join(dirname(realpathSync(fileURLToPath(import.meta.url))), "../../.agents/skills/calibrated-judgment/references");
const GOAL_REF = "goal-comprehension.md";
const SOLUTION_REF = "solution-confidence.md";

// --- question wordings ----------------------------------------------------------

// Verbatim from goal-comprehension.md; do not paraphrase without re-running its cases.
const BLAST_RADIUS = {
  type: "score" as const,
  instructions: "The operationalization claims to be what the user's words mean. If that reading is WRONG, how much of the work already committed downstream does it invalidate?",
  criteria: ["one word or a phrasing", "one section or one paragraph", "the structure of the whole thing"] as const,
};
// Choices differ in kind, not degree: where Jev routed well (map: 4/6, all misses were degree).
const REPLY = {
  type: "choice" as const,
  instructions: "The agent showed the user `draft` (a goal, criteria, and any questions). How does the user's `reply` respond to it?",
  criteria: {
    confirm: "explicitly accepts the draft (yes, ok, agree, go ahead, picks what the draft already assumes, or leaves a question to the agent's choice); a side question next to an explicit acceptance still accepts",
    amend: "wants something changed, added, or removed, or picks an answer to a question that the draft does not assume",
    reject: "says the draft misses what they want",
    other: "only asks questions or talks about something else, without explicitly accepting the draft",
  },
};
// Only a real question pauses the gate. Asking "is it claiming done?" was gameable: a final
// report that described its next steps read as progress (0.70) and skipped review entirely.
const STOP_KIND = {
  type: "choice" as const,
  instructions: "The agent ended its turn with `message`. Does it end by asking the user something it needs answered before it can go on?",
  criteria: {
    asking: "ends with a question or a decision the user must answer before the agent can continue",
    other: "anything else: a result, a report, a summary, a plan, or a description of what comes next",
  },
};
const WASTE = {
  type: "score" as const,
  instructions: "If the approach in `approach` turns out to be WRONG, how much of the execution it commits would be wasted?",
  criteria: ["one line or one function", "one module or one feature", "the structure of the whole application"] as const,
};
const approachMeets = (i: number) => ({
  type: "noul" as const,
  instructions: `Executing \`approach\` as written would satisfy \`criteria[${i}]\`.`,
  criteria: { true: "the approach as written delivers this criterion", false: "the approach misses it, contradicts it, or does not say enough to tell" },
});
const evidenceMeets = (i: number) => ({
  type: "noul" as const,
  instructions: `\`evidence.c${i}\` (tool output the agent cited for this criterion, verified verbatim) and \`final_message\` show that \`criteria[${i}]\` is met.`,
  criteria: { true: "the evidence shows this criterion is met", false: "the evidence shows it is not met, or does not establish it" },
});

// --- transcript + Jev helpers --------------------------------------------------

/** Text of one message's content: a string, or its text parts plus a short line per tool call. */
function text(content: unknown, max: number): string {
  if (typeof content === "string") return content.slice(0, max);
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const part of content) {
    if (typeof part !== "object" || part === null || !("type" in part)) continue;
    if (part.type === "text" && "text" in part && typeof part.text === "string") parts.push(part.text);
    else if (part.type === "toolCall" && "name" in part) parts.push(`[call ${String(part.name)}]`);
  }
  return parts.join("\n").slice(0, max);
}

type Answers = SystemOneResult<Questions>["answers"];

async function ask(state: Record<string, unknown>, questions: Questions): Promise<Answers | null> {
  if (!jevClient) return null;
  try {
    const result = await jevClient.systemOne({ state: JSON.parse(JSON.stringify(state)), questions });
    return result.answers;
  } catch (err) {
    console.error("[jev-pilot] Jev call failed:", err);
    return null;
  }
}
function noul(a: Answers, key: string): number | undefined {
  const r = a[key];
  return r?.type === "noul" ? r.noul : undefined;
}
function probability(a: Answers, key: string, level: string): number | undefined {
  const r = a[key];
  return r?.type === "score" ? r.probabilities[level] : undefined;
}
function chosen(a: Answers, key: string): string {
  const r = a[key];
  return r?.type === "choice" ? r.choice : "";
}
const pct = (x: number | undefined) => (x === undefined ? "?" : `${Math.round(x * 100)}%`);
const reply = (lines: string[]) => ({ content: [{ type: "text" as const, text: lines.join("\n") }] });
/** An oracle's answer, as it appears in the transcript once a consultation completes. */
const ORACLE_ANSWER = /<task-result[^>]*agent="oracle"[^>]*status="completed"/;
const MUTATING = new Set(["edit", "write", "ast_edit"]);

// --- extension ----------------------------------------------------------------

export default function jevPilot(pi: ExtensionAPI) {
  const fresh = () => ({
    active: false, phase: "inactive" as Phase,
    goal: null as string | null, criteria: [] as Criterion[],
    // Keyed D1..Dn with readings a/b, exactly as the user saw them, so "D1 (b)" is readable.
    draft: null as { goal: string; criteria: Criterion[]; asked: Record<string, { question: string; "a (draft assumes)": string; b: string }> } | null,
    awaitingUser: false,
    lockedAt: 0, proposed: false,
    criterionScores: [] as (number | undefined)[],
    why: [] as string[],            // per criterion, what Jev judged when it said no: shown to the user
    approach: null as string | null,
    lastReply: null as { prompt: string; result: unknown } | null,
    newWords: [] as string[], evidence: [] as string[], refsRead: new Set<string>(),
    recentToolCalls: [] as string[], consecutiveErrors: 0,
    reviewInjected: false, blockCount: 0, detail: "", redirects: 0,
    cited: [] as string[][],        // per criterion, excerpts the agent cited in pilot_report
    nudges: 0,                      // stops without pilot_report; separate from the completion blocks
  });
  let state = fresh();
  const setPhase = (p: Phase) => { state.phase = p; };

  // --- UI: one chip in the pi status bar; a widget only while criteria are failing ---

  const mark = (s: number | undefined) => (s === undefined ? "·" : s >= PASS ? "✓" : "✗");
  function render(ctx: ExtensionContext, detail?: string) {
    if (detail !== undefined) state.detail = detail;
    const scored = state.phase === "completion" ? state.criterionScores.filter((s): s is number => s !== undefined) : [];
    const tally = scored.length ? ` ✓${scored.filter(s => s >= PASS).length}/${state.criteria.length}` : "";
    ctx.ui.setStatus("jev-pilot", state.active ? `${ICON[state.phase]} ${state.phase}${tally}${state.detail ? ` · ${state.detail}` : ""}` : undefined);
    // One line per criterion Jev said no to, with what it judged, so the user can tell noise from a real gap.
    const failing = state.criteria.flatMap((c, i) => {
      const s = state.criterionScores[i];
      return state.why[i] && (s === undefined || s < PASS) ? [`${s === undefined ? "✗" : state.phase === "completion" ? "✗" : "⚠"} ${c.label}  ${pct(s)}  · ${state.why[i]}`] : [];
    });
    const shown = failing.length > 3 ? [...failing.slice(0, 2), `… ${failing.length - 2} more (/pilot show)`] : failing;
    ctx.ui.setWidget("jev-pilot", shown.length ? shown : undefined, { placement: "aboveEditor" });
  }
  // Text the pilot itself injects comes back through before_agent_start as a prompt; it is not the user.
  const said = new Set<string>();
  const mine = (words: string) => [...said].some(t => t === words || (words.length > 40 && t.startsWith(words.slice(0, 200))));
  function goalBlock(): string {
    return [
      "# jev-pilot: the agreed goal (keep working toward it; the user agreed these words)",
      `Goal: ${state.goal}`,
      ...state.criteria.map((c, i) => `${i + 1}. ${c.label}${c.kind === "process" ? " (process)" : ""}: ${c.criterion}`),
      ...(state.approach ? [`Approach proposed: ${state.approach}`] : []),
    ].join("\n");
  }
  function clearUI(ctx: ExtensionContext) {
    ctx.ui.setStatus("jev-pilot", undefined);
    ctx.ui.setWidget("jev-pilot", undefined);
  }
  const notify = (ctx: ExtensionContext, msg: string, type: "info" | "warning" = "info") => ctx.ui.notify(msg, type);
  const steer = (content: string) => pi.sendMessage({ customType: "jev-pilot", content }, { deliverAs: "steer" });
  const message = (content: string): { message: PilotMessage } => ({ message: { customType: "jev-pilot", content } });
  // session_stop continuations come back through before_agent_start; record them so they are not read as the user.
  const again = (content: string) => { said.add(content.trim()); return { continue: true, additionalContext: content }; };
  const blockWith = (content: string) => { said.add(content.trim()); return { decision: "block" as const, reason: content }; };

  /** Text of every branch entry after `from`: messages, tool results, and delivered custom messages. */
  function branchText(ctx: ExtensionContext, from: number): string {
    const out: string[] = [];
    ctx.sessionManager.getBranch().slice(from).forEach((entry) => {
      if (entry.type === "message" && "content" in entry.message) out.push(text(entry.message.content, 200_000));
      else if (entry.type === "custom_message") out.push(text(entry.content, 200_000));
    });
    return out.join("\n");
  }
  function recentUserWords(ctx: ExtensionContext): string {
    const out: string[] = [];
    for (const entry of ctx.sessionManager.getBranch()) {
      if (entry.type !== "message" || entry.message.role !== "user") continue;
      const t = text(entry.message.content, 4000).trim();
      if (t && !t.startsWith("/")) out.push(t);
    }
    return out.slice(-6).join("\n\n") || "(none)";
  }
  function detectStuck(): string | null {
    if (state.consecutiveErrors >= 3) return `${state.consecutiveErrors} consecutive errors`;
    const calls = state.recentToolCalls;
    if (calls.length >= 9) {
      const recent = calls.slice(-3).join(",");
      let repeats = 0;
      for (let i = calls.length - 6; i >= 0; i -= 3) {
        if (calls.slice(i, i + 3).join(",") === recent) repeats++;
        else break;
      }
      if (repeats >= 2) return `same tool pattern ${repeats + 1}x`;
    }
    return null;
  }
  const tag = (c: Criterion) => (c.kind === "process" ? " (process)" : "");
  const criteriaList = (cs: Criterion[]) => cs.map((c, i) => `${i + 1}. **${c.label}**${tag(c)}: ${c.criterion}`);

  // =====================================================================
  // /pilot
  // =====================================================================

  pi.registerCommand("pilot", {
    description: "Toggle jev-pilot (agreed goal, consulted approach, verified completion); `/pilot show` lists the goal and criteria",
    handler: async (args, ctx) => {
      if (args.trim() === "show") {
        const goal = state.goal ?? state.draft?.goal;
        const cs = state.goal ? state.criteria : state.draft?.criteria ?? [];
        notify(ctx, goal
          ? [`${ICON.goal} ${goal}${state.goal ? "" : "  (draft, not agreed yet)"}`, ...cs.map((c, i) => `${mark(state.criterionScores[i])} ${c.label}${tag(c)}: ${c.criterion}`)].join("\n")
          : state.active ? "jev-pilot: no goal drafted yet" : "jev-pilot is off");
        return;
      }
      if (state.active) {
        state = fresh();
        clearUI(ctx);
        notify(ctx, "jev-pilot off");
        return;
      }
      if (![GOAL_REF, SOLUTION_REF].every(f => existsSync(join(REF, f)))) {
        ctx.ui.notify(`jev-pilot not activated: phase references missing under ${REF}`, "error");
        return;
      }
      const jev = await connectJev(ctx);
      if (typeof jev === "string") {
        ctx.ui.notify(`jev-pilot not activated: ${jev}`, "error");
        return;
      }
      jevClient = jev;
      state = fresh();
      state.active = true;
      setPhase("goal");
      render(ctx, "drafting");
      notify(ctx, `${ICON.goal} jev-pilot on`);
      steer([
        `${ICON.goal} **jev-pilot on: goal phase.** Before any work:`,
        `1. Read \`${REF}/goal-comprehension.md\`, then read the ground the task touches (code, data, docs). What the user does not know they do not know mostly lives there.`,
        "2. Call `pilot_set_goal` with the goal, criteria (each with a 3-5 word `label`), and every open question you found, each with the reading you would pick and its rival. Jev ranks the questions by what a wrong reading would cost.",
        "3. Show the user the draft and the questions Jev sends to them, then stop and wait. Nothing is edited until they agree.",
      ].join("\n"));
    },
  });

  // =====================================================================
  // pilot_set_goal: a draft for the user, with questions ranked by blast radius
  // =====================================================================

  const z = pi.zod;
  pi.registerTool({
    name: "pilot_set_goal",
    label: "Draft Pilot Goal",
    description: "jev-pilot: draft the goal, criteria, and open questions for the user to agree. Call it again whenever the user amends it or changes what they want.",
    parameters: z.object({
      goal: z.string().describe("What the user wants achieved, one sentence"),
      criteria: z.array(z.object({
        label: z.string().describe("3-5 words, shown in the status bar"),
        criterion: z.string().describe("One checkable demand, stated concretely; a threshold is an absolute number (\"20s or less\"), never relative (\"half of the current 40s\")"),
        kind: z.enum(["product", "process"]).default("product").describe("process: a demand about how the work is done or reported (\"runs live in this session\", \"final report in chat\"), which no plan can show in advance; product: anything the finished work itself must have"),
      })).min(1),
      questions: z.array(z.object({
        question: z.string().describe("The open question, as you would ask the user"),
        reading: z.string().describe("The answer you would assume if you did not ask"),
        rival: z.string().describe("The strongest other answer"),
      })).default(() => []).describe("Every place the user's words, or what you found, leave more than one reading open"),
    }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      if (!state.active) return reply(["jev-pilot is off. The user turns it on with /pilot."]);
      if (!state.refsRead.has(GOAL_REF)) return reply([`Not recorded: read \`${REF}/${GOAL_REF}\` first, then draft again.`]);
      const s = state;
      render(ctx, params.questions.length ? "ranking questions" : "");
      const user_words = recentUserWords(ctx);
      const ranked = await Promise.all(params.questions.map(async (q) => {
        const a = await ask({ user_words, operationalization: q.reading, rival_reading: q.rival }, { radius: BLAST_RADIUS });
        return { ...q, structure: a ? probability(a, "radius", "2") : undefined };
      }));
      if (state !== s) return reply(["jev-pilot was reset while the goal was being drafted; nothing recorded."]);
      ranked.sort((a, b) => (b.structure ?? 1) - (a.structure ?? 1));
      // Unranked (Jev down) questions go to the user: the safe side of the filter.
      const toUser = ranked.filter(q => (q.structure ?? 1) >= ASK_USER_AT);
      const toAgent = ranked.filter(q => (q.structure ?? 1) < ASK_USER_AT);

      const update = s.goal !== null;
      Object.assign(s, {
        draft: { goal: params.goal, criteria: params.criteria, asked: Object.fromEntries(toUser.map((q, i) => [`D${i + 1}`, { question: q.question, "a (draft assumes)": q.reading, b: q.rival }])) },
        awaitingUser: true, proposed: false, reviewInjected: false, blockCount: 0, criterionScores: [], why: [], newWords: [], cited: [], lastReply: null,
      });
      setPhase("goal");
      const counts = [toUser.length ? `${toUser.length} to you` : "", toAgent.length ? `${toAgent.length} decided` : ""].filter(Boolean).join(", ");
      render(ctx, counts || "waiting for you");
      return reply([
        `Draft recorded${update ? " (the agreed goal is suspended until the user agrees this one)" : ""}. Show the user now, in chat:`,
        `- the goal: ${params.goal}`,
        "- the criteria, numbered:", ...criteriaList(params.criteria).map(l => `  ${l}`),
        ...(toUser.length ? ["- these questions, numbered D1..Dn, each with both readings (a wrong reading here costs the most):",
          ...toUser.map((q, i) => `  D${i + 1}. ${q.question} (a) ${q.reading} (b) ${q.rival}  [structure ${pct(q.structure)}]`)] : []),
        ...(toAgent.length ? ["- decided by you, one line each so the user can overrule (a wrong reading is cheap):",
          ...toAgent.map(q => `  ${q.question} → ${q.reading}  [structure ${pct(q.structure)}]`)] : []),
        "Then stop and wait for their reply. The pilot reads it: agree, amend, or reject.",
      ]);
    },
  });

  // =====================================================================
  // pilot_propose: after the consultation; Jev warns, never blocks
  // =====================================================================

  pi.registerTool({
    name: "pilot_propose",
    label: "Propose Approach",
    description: "jev-pilot: after consulting an oracle, submit the approach; Jev flags criteria it would miss before you execute.",
    parameters: z.object({
      approach: z.string().describe("The approach, specific enough to execute without asking, revised from the oracle's answer"),
    }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      if (!state.active || !state.goal) return reply([`jev-pilot is not waiting for an approach (phase: ${state.phase}${state.awaitingUser ? ", the goal is waiting for the user" : ""}).`]);
      if (!state.refsRead.has(SOLUTION_REF)) return reply([`Not recorded: read \`${REF}/${SOLUTION_REF}\` first, then propose again.`]);
      if (!ORACLE_ANSWER.test(branchText(ctx, state.lockedAt))) {
        return reply([
          "Not recorded: no oracle has answered since the goal was agreed.",
          'Call `task` with agent "oracle", giving it the goal, what you found, and this approach, asking what is wrong with it. Wait for its answer, revise, then call `pilot_propose` again.',
        ]);
      }
      const s = state;
      render(ctx, "Jev reading the approach");
      const questions: Questions = { waste: WASTE };
      // Full criteria stay in the state so `criteria[i]` indexes match; only product criteria are asked.
      const product = s.criteria.flatMap((c, i) => (c.kind === "process" ? [] : [i]));
      product.forEach((i) => { questions[`c${i}`] = approachMeets(i); });
      const a = await ask({ goal: s.goal, criteria: s.criteria.map(c => c.criterion), approach: params.approach }, questions);
      if (state !== s) return reply(["jev-pilot was reset while the approach was being read."]);
      s.proposed = true;
      s.approach = params.approach;
      setPhase("execution");
      if (!a) {
        render(ctx, "Jev unreachable");
        return reply(["Recorded; Jev was unreachable, so the approach was not read. Execute, and verify each criterion yourself."]);
      }
      s.criterionScores = s.criteria.map((_, i) => noul(a, `c${i}`));
      s.why = s.criteria.map((_, i) => (product.includes(i) && (s.criterionScores[i] ?? 0) < PASS ? "plan only" : ""));
      const doubts = product.flatMap(i => ((s.criterionScores[i] ?? 0) < PASS ? [`- ${s.criteria[i].label} (${pct(s.criterionScores[i])})`] : []));
      const structure = probability(a, "waste", "2");
      render(ctx, product.length ? `Jev ${doubts.length ? "⚠" : "✓"}${product.length - doubts.length}/${product.length}` : "");
      return reply([
        "Recorded. Execute it.",
        ...(doubts.length ? ["Jev doubts the approach as written delivers these. Revise if it has a point; if you disagree, proceed and say why in your report:", ...doubts] : []),
        ...((structure ?? 0) > STRUCTURE_WARN ? [`If this approach is wrong it costs the structure (${pct(structure)}): tell the user before a large change.`] : []),
      ]);
    },
  });

  // =====================================================================
  // pilot_report: the review's evidence, one set per criterion, checked verbatim in code
  // =====================================================================

  const squash = (t: string) => t.replace(/\s+/g, " ").trim();
  pi.registerTool({
    name: "pilot_report",
    label: "Report Evidence",
    description: "jev-pilot review: for each criterion, cite the tool output that shows it met, copied verbatim. Jev judges each criterion against its own citations.",
    parameters: z.object({
      items: z.array(z.object({
        n: z.number().describe("Criterion number, 1-based"),
        evidence: z.string().describe("An excerpt copied exactly from a tool output in this session"),
      })).min(1),
    }),
    async execute(_id, params) {
      const s = state;
      if (!s.active || (s.phase !== "review" && s.phase !== "completion")) return reply([`jev-pilot is not in review (phase: ${s.phase}).`]);
      const recorded = s.evidence.map(squash);
      const bad = params.items.filter(it => it.n < 1 || it.n > s.criteria.length || !squash(it.evidence) || !recorded.some(r => r.includes(squash(it.evidence))));
      if (bad.length) return reply(["Not recorded: these are not verbatim tool output from this session (or name no criterion):", ...bad.map(b => `- ${b.n}: "${b.evidence.slice(0, 120)}"`), "Copy the excerpt exactly, or run the tool to produce it, then report again."]);
      s.cited = s.criteria.map((_, i) => params.items.filter(it => it.n === i + 1).map(it => it.evidence.slice(0, CITE_CHARS)));
      const missing = s.criteria.flatMap((c, i) => (s.cited[i].length || c.kind === "process" ? [] : [`${i + 1}. ${c.label}`]));
      return reply(missing.length ? ["Recorded. No citation yet for:", ...missing, "Add them with another `pilot_report` (it replaces this one), or finish if the final message carries them."] : ["Recorded. Finish; Jev checks each criterion against its citations and your final message."]);
    },
  });

  // =====================================================================
  // The user's reply to a draft; words that arrive after the goal is agreed
  // =====================================================================

  pi.on("before_agent_start", async (event, ctx) => {
    if (!state.active) return;
    const words = event.prompt.trim();
    // Every return carries the agreed goal in the system prompt, so it survives compaction.
    const withGoal = (r: { message?: PilotMessage } = {}) =>
      state.goal && !state.awaitingUser ? { ...r, systemPrompt: [...(event.systemPrompt ?? []), goalBlock()] } : (r.message ? r : undefined);
    if (!words || mine(words)) return withGoal();
    if (!state.awaitingUser || !state.draft) {
      if (state.goal) state.newWords.push(words);
      return withGoal();
    }
    // A policy retry re-runs this handler for the same prompt: answer it once.
    if (state.lastReply?.prompt === words) return withGoal(state.lastReply.result as { message?: PilotMessage });
    const s = state;
    const draft = s.draft;
    const a = await ask({ draft: { goal: draft.goal, criteria: draft.criteria.map(c => c.criterion), questions: draft.asked }, reply: words }, { reply: REPLY });
    if (state !== s || !draft) return;
    const verdict = a ? chosen(a, "reply") : "other";
    let result: { message: PilotMessage };
    if (verdict === "confirm") {
      Object.assign(s, { goal: draft.goal, criteria: draft.criteria, draft: null, awaitingUser: false, lockedAt: ctx.sessionManager.getBranch().length, evidence: [], cited: [], approach: null });
      setPhase("solution");
      render(ctx, `agreed · ${s.criteria.length} criteria`);
      result = message([
        `${ICON.solution} jev-pilot: the user agreed the goal. Solution phase:`,
        `1. Read \`${REF}/solution-confidence.md\`.`,
        '2. Draft the approach, then consult: `task` with agent "oracle", giving it what you found and the approach; ask what is wrong with it. The pilot adds the goal to every `task` call. Wait for the answer.',
        "3. Revise, then call `pilot_propose`. Edits stay blocked until then.",
        "If their reply also answered questions, fold the answers into the approach. If it asked a side question, answer it; if your answer changes the goal, call `pilot_set_goal` again.",
      ].join("\n"));
    } else if (verdict === "amend" || verdict === "reject") {
      render(ctx, "revising");
      result = message(verdict === "amend"
        ? `${ICON.goal} jev-pilot: the user wants the draft changed. Revise it from their reply, call \`pilot_set_goal\` again, and show them the new draft.`
        : `${ICON.goal} jev-pilot: the user says the draft misses what they want. Re-read their words with \`${REF}/goal-comprehension.md\`, check the ground again, and draft anew with \`pilot_set_goal\`.`);
    } else {
      result = message(`${ICON.goal} jev-pilot: the goal draft is still waiting for the user's agreement. Answer them, then remind them the draft needs a yes, a change, or a no.`);
    }
    s.lastReply = { prompt: words, result };
    return withGoal(result);
  });

  // =====================================================================
  // Guard, evidence, stuck
  // =====================================================================

  pi.on("tool_call", async (event) => {
    if (!state.active) return;
    const name = event.toolName.replace(/^_/, "");
    const path = typeof event.input.path === "string" ? event.input.path : "";
    if (MUTATING.has(name) && !path.startsWith("xd://") && (state.phase === "goal" || state.phase === "solution")) {
      return { block: true, reason: state.phase === "goal"
        ? "jev-pilot: no edits before the user agrees the goal. Call `pilot_set_goal` and wait for their reply."
        : "jev-pilot: no edits before the approach is proposed. Consult an oracle, then call `pilot_propose`." };
    }
    if (state.phase === "execution" || state.phase === "review") {
      state.recentToolCalls.push(name);
      if (state.recentToolCalls.length > 20) state.recentToolCalls.shift();
    }
    // Subagents start blank: every task call carries the agreed goal. Single-task schemas have no
    // `context` (it would be stripped on revalidation), so the goal goes into `task` there.
    if (name === "task" && state.goal && !state.awaitingUser) {
      const block = goalBlock();
      const field = Array.isArray(event.input.tasks) ? "context" : "task";
      const current = typeof event.input[field] === "string" ? event.input[field] : "";
      if (!current.includes("# jev-pilot: the agreed goal")) return { input: { ...event.input, [field]: current ? `${current}\n\n${block}` : block } };
    }
  });

  pi.on("tool_result", async (event) => {
    if (!state.active) return;
    const path = typeof event.input.path === "string" ? event.input.path : "";
    if (event.toolName.replace(/^_/, "") === "read" && !event.isError) {
      const base = path.replace(/:[^/]*$/, "").split("/").pop() ?? "";
      if (base === GOAL_REF || base === SOLUTION_REF) { state.refsRead.add(base); return; }
    }
    if (!state.goal || path.startsWith("xd://pilot")) return;
    const input = JSON.stringify(event.input).slice(0, 300);
    const output = text(event.content, RECORD_CHARS);
    state.evidence.push(`[${event.toolName}${event.isError ? " ERROR" : ""}] ${input}\n${output}`);
    if (state.phase === "execution" || state.phase === "review") state.consecutiveErrors = event.isError ? state.consecutiveErrors + 1 : 0;
  });

  pi.on("turn_end", async (_event, ctx) => {
    if (!state.active || (state.phase !== "execution" && state.phase !== "review")) return;
    const stuck = detectStuck();
    if (!stuck) return;
    state.recentToolCalls = [];
    state.consecutiveErrors = 0;
    notify(ctx, `${ICON.stuck} Stuck: ${stuck}`, "warning");
    steer(`${ICON.stuck} **jev-pilot: stuck (${stuck}).** Step back: re-read the goal and what you found, and change the approach rather than repeating it.`);
  });

  // =====================================================================
  // session_stop: only a question for the user pauses; any other stop goes to review, then completion
  // =====================================================================

  pi.on("session_stop", async (event, ctx) => {
    if (!state.active || !state.goal || state.phase === "goal") return;
    const s = state;
    const last = event.last_assistant_message && "content" in event.last_assistant_message ? text(event.last_assistant_message.content, 4000) : "";

    const kind = await ask({ message: last || "(empty)" }, { kind: STOP_KIND });
    if (state !== s) return;
    if (kind && chosen(kind, "kind") === "asking") return; // Jev down counts as a stop: the safe side

    if (s.newWords.length) {
      const words = s.newWords.splice(0);
      return again([
        `${ICON.goal} jev-pilot: the user wrote ${words.length} message(s) since the goal was agreed:`,
        ...words.map(w => `- "${w.length > 400 ? `${w.slice(0, 400)}…` : w}"`),
        "If any of them changes or adds to what they want, call `pilot_set_goal` with the updated draft and show it to them. If not, finish again.",
      ].join("\n"));
    }

    if (s.phase === "solution" && !s.proposed) {
      if (s.redirects >= MAX_REDIRECTS) return;
      s.redirects++;
      return again(`${ICON.solution} jev-pilot: not proposed yet (${s.redirects}/${MAX_REDIRECTS}). Consult an oracle on the approach, then call \`pilot_propose\` before executing or finishing.`);
    }

    if (!s.reviewInjected) {
      s.reviewInjected = true;
      setPhase("review");
      Object.assign(s, { criterionScores: [], why: [] }); // the plan's doubts are stale once the work is done
      render(ctx, "");
      return again([
        `${ICON.review} jev-pilot review. Read \`${REF}/review-verification.md\`, then for each criterion produce real evidence with a tool (run it, read the file, show the diff):`,
        ...criteriaList(s.criteria),
        "Then call `pilot_report` with, for each criterion, the excerpt of tool output that shows it, copied exactly. Jev judges each criterion against its own citations only.",
        "Jev does not compare numbers: for a criterion with a threshold, write the comparison in your final message, e.g. `31.2s > 20s limit: not met`. Then finish.",
      ].join("\n"));
    }

    if (!s.cited.length && s.nudges < MAX_REDIRECTS) {
      s.nudges++;
      render(ctx, `no report [${s.nudges}/${MAX_REDIRECTS}]`);
      return again(`${ICON.review} jev-pilot: no \`pilot_report\` yet (${s.nudges}/${MAX_REDIRECTS}). Cite the tool output for each criterion with \`pilot_report\`, then finish.`);
    }
    setPhase("completion");
    render(ctx, "Jev checking");
    const cited: Record<string, string[]> = {};
    s.criteria.forEach((_, i) => { cited[`c${i}`] = s.cited[i] ?? []; });
    const questions: Questions = {};
    s.criteria.forEach((_, i) => { questions[`c${i}`] = evidenceMeets(i); });
    const a = await ask({ goal: s.goal, criteria: s.criteria.map(c => c.criterion), evidence: cited, final_message: last }, questions);
    if (state !== s) return;
    if (!a) {
      state = fresh();
      clearUI(ctx);
      notify(ctx, `${ICON.blocked} Jev unreachable: completion not checked. Pilot off.`, "warning");
      return again("jev-pilot: Jev was unreachable, so completion was not checked. Tell the user the criteria are unverified.");
    }
    s.criterionScores = s.criteria.map((_, i) => noul(a, `c${i}`));
    s.why = s.criteria.map((_, i) => ((s.criterionScores[i] ?? 0) >= PASS ? "" : s.cited[i]?.length ? `cited: "${squash(s.cited[i][0]).slice(0, 60)}"` : "no citation"));
    const failing = s.criteria.flatMap((c, i) => ((s.criterionScores[i] ?? 0) < PASS ? [`- ${c.label}: ${c.criterion} (${pct(s.criterionScores[i])})`] : []));

    if (failing.length) {
      s.blockCount++;
      if (s.blockCount >= MAX_BLOCKS) {
        state = fresh();
        clearUI(ctx);
        notify(ctx, `${ICON.blocked} Released unverified after ${MAX_BLOCKS} blocks. Pilot off.`, "warning");
        return again([
          `jev-pilot: released after ${MAX_BLOCKS} blocks; these criteria are UNVERIFIED:`, ...failing,
          "Tell the user plainly which criteria are unverified and why. The pilot is off.",
        ].join("\n"));
      }
      render(ctx, `blocked [${s.blockCount}/${MAX_BLOCKS}]`);
      notify(ctx, `${ICON.blocked} Not done: ${failing.length} criteria unmet`, "warning");
      return blockWith([
        `jev-pilot: not done (${s.blockCount}/${MAX_BLOCKS}). Your citations do not show these criteria met:`, ...failing,
        "Do the work or produce the evidence with a tool, cite it again with `pilot_report`, then finish. For a threshold, write the comparison in your final message.",
      ].join("\n"));
    }

    // Success stays quiet: the chip shows the result instead of a popup, until the next /pilot or restart.
    const n = s.criteria.length;
    state = fresh();
    ctx.ui.setWidget("jev-pilot", undefined);
    ctx.ui.setStatus("jev-pilot", `${ICON.done} completion ✓${n}/${n}`);
  });

  pi.on("session_start", async (_event, ctx) => { state = fresh(); clearUI(ctx); });
}
