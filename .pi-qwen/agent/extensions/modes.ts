/**
 * Mode Cycling Extension
 *
 * Cicla entre 4 modos de interacción (como Claude Code):
 *   auto  → todo directo, sin fricción
 *   plan  → exploración read-only (edit/write bloqueados, bash restrictivo)
 *   manual → pide aprobación antes de cada tool call
 *   accepts → intercepta edit/write, muestra diff antes de aplicar
 *
 * Shortcut: Shift+Tab para ciclar entre modos.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { ToolCallEvent } from "@earendil-works/pi-coding-agent";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { AssistantMessage, TextContent } from "@earendil-works/pi-ai";
import { Key } from "@earendil-works/pi-tui";

// ─── Tools por modo ───────────────────────────────────────────────────────────

const ALL_TOOLS = ["read", "bash", "edit", "write", "grep", "find", "ls"];
const PLAN_DISABLED = new Set(["edit", "write"]);
const MANUAL_EXTRA = ["questionnaire"];

function getToolsForMode(mode: Mode, currentTools: string[]): string[] {
	switch (mode) {
		case "auto":
			return [...new Set([...ALL_TOOLS, ...currentTools.filter((t) => !ALL_TOOLS.includes(t))])];
		case "plan":
			return [...new Set([...ALL_TOOLS.filter((t) => !PLAN_DISABLED.has(t)), ...currentTools.filter((t) => !ALL_TOOLS.includes(t))])];
		case "manual":
			return [...new Set([...ALL_TOOLS, ...MANUAL_EXTRA, ...currentTools.filter((t) => !ALL_TOOLS.includes(t) && !MANUAL_EXTRA.includes(t))])];
		case "accepts":
			return [...new Set([...ALL_TOOLS, ...currentTools.filter((t) => !ALL_TOOLS.includes(t))])];
	}
}

// ─── Bash allowlist para plan mode ────────────────────────────────────────────

const SAFE_BASH = [
	/^\s*(cat|head|tail|less|more|grep|find|rg|fd|ls|pwd|echo|printf|wc|sort|uniq|diff|file|stat|du|df|tree|which|whereis|type|env|printenv|uname|whoami|id|date|cal|uptime|ps|top|htop|free)\b/,
	/^\s*git\s+(status|log|diff|show|branch|remote|config\s+--get|ls-)/i,
	/^\s*npm\s+(list|ls|view|info|search|outdated|audit)\b/i,
	/^\s*yarn\s+(list|info|why|audit)\b/i,
	/^\s*node\s+--version/i,
	/^\s*python\s+--version/i,
	/^\s*curl\s/i,
	/^\s*jq\b/,
	/^\s*sed\s+-n/i,
	/^\s*awk\b/,
	/^\s*bat\b/,
	/^\s*eza\b/,
];

function isSafeBashCommand(cmd: string): boolean {
	return SAFE_BASH.some((p) => p.test(cmd));
}

// ─── Types ────────────────────────────────────────────────────────────────────

type Mode = "auto" | "plan" | "manual" | "accepts";

const MODE_LABELS: Record<Mode, string> = {
	auto: "🚀 auto",
	plan: "📋 plan",
	manual: "🛡 manual",
	accepts: "✅ accepts",
};

const MODE_ORDER: Mode[] = ["auto", "plan", "manual", "accepts"];

interface ModeState {
	mode: Mode;
	toolsBeforeMode?: string[];
	acceptedEdits?: string[]; // paths ya aprobados en accepts mode
}

// ─── Type guards ──────────────────────────────────────────────────────────────

function isAssistantMessage(m: AgentMessage): m is AssistantMessage {
	return m.role === "assistant" && Array.isArray(m.content);
}

function getTextContent(message: AssistantMessage): string {
	return message.content
		.filter((block): block is TextContent => block.type === "text")
		.map((block) => block.text)
		.join("\n");
}

// ─── Extension ────────────────────────────────────────────────────────────────

export default function modeExtension(pi: ExtensionAPI): void {
	let state: ModeState = { mode: "auto" };
	let toolsBeforeMode: string[] | undefined;

	// ── Helpers ──

	function cycleMode(): void {
		const currentIdx = MODE_ORDER.indexOf(state.mode);
		state.mode = MODE_ORDER[(currentIdx + 1) % MODE_ORDER.length];

		const newTools = getToolsForMode(state.mode, pi.getActiveTools());
		pi.setActiveTools(newTools);
	}

	function applyModeToTools(ctx: ExtensionContext): void {
		if (state.mode === "auto") {
			pi.setActiveTools(toolsBeforeMode ?? ALL_TOOLS);
		} else {
			const newTools = getToolsForMode(state.mode, toolsBeforeMode ?? pi.getActiveTools());
			pi.setActiveTools(newTools);
		}
	}

	function updateStatus(ctx: ExtensionContext): void {
		ctx.ui.setStatus("mode", ctx.ui.theme.fg("accent", MODE_LABELS[state.mode]));
	}

	function persistState(): void {
		pi.appendEntry("mode-state", state);
	}

	// ── Shortcut ──

	pi.registerShortcut(Key.shift("tab"), {
		description: "Cycle interaction mode (auto → plan → manual → accepts)",
		handler: async (ctx) => {
			cycleMode();
			applyModeToTools(ctx);
			updateStatus(ctx);
			persistState();
			ctx.ui.notify(`Mode: ${MODE_LABELS[state.mode]}`, "info");
		},
	});

	// ── Slash commands ──

	pi.registerCommand("mode", {
		description: "Show current interaction mode",
		handler: async (_args, ctx) => {
			ctx.ui.notify(`Current mode: ${MODE_LABELS[state.mode]}`, "info");
		},
	});

	pi.registerCommand("mode-auto", {
		description: "Switch to auto mode",
		handler: async (args, ctx) => {
			state.mode = "auto";
			applyModeToTools(ctx);
			updateStatus(ctx);
			persistState();
			ctx.ui.notify("Mode: auto — all tools unrestricted", "info");
		},
	});

	pi.registerCommand("mode-plan", {
		description: "Switch to plan mode (read-only)",
		handler: async (args, ctx) => {
			state.mode = "plan";
			applyModeToTools(ctx);
			updateStatus(ctx);
			persistState();
			ctx.ui.notify("Mode: plan — read-only exploration, write tools disabled", "info");
		},
	});

	pi.registerCommand("mode-manual", {
		description: "Switch to manual mode (approve each action)",
		handler: async (args, ctx) => {
			state.mode = "manual";
			applyModeToTools(ctx);
			updateStatus(ctx);
			persistState();
			ctx.ui.notify("Mode: manual — approval required for each tool call", "info");
		},
	});

	pi.registerCommand("mode-accepts", {
		description: "Switch to accepts mode (approve edits before applying)",
		handler: async (args, ctx) => {
			state.mode = "accepts";
			applyModeToTools(ctx);
			updateStatus(ctx);
			persistState();
			ctx.ui.notify("Mode: accepts — shows diffs before applying edits", "info");
		},
	});

	// ── Plan mode: block destructive bash ──

	pi.on("tool_call", async (event: ToolCallEvent, ctx) => {
		if (state.mode === "plan" && event.toolName === "bash") {
			const command = event.input.command as string;
			if (!isSafeBashCommand(command)) {
				return {
					block: true,
					reason: `Plan mode: command blocked (not allowlisted).\nCommand: ${command}\nUse /mode-auto to switch to auto mode.`,
				};
			}
		}

		// Manual mode: ask approval for every tool call
		if (state.mode === "manual" && event.toolName !== "questionnaire") {
			const toolInput = JSON.stringify(event.input, null, 2);
			const approved = await ctx.ui.confirm(
				`Approve ${event.toolName}?`,
				toolInput,
			);
			if (!approved) {
				return {
					block: true,
					reason: `Tool call blocked by user in manual mode.`,
				};
			}
		}

		// Accepts mode: intercept edit/write, show diff
		if (state.mode === "accepts" && (event.toolName === "edit" || event.toolName === "write")) {
			const path = event.input.path as string;

			// Already approved this path? Skip.
			if (state.acceptedEdits?.includes(path)) {
				return;
			}

			let diffText = "";

			if (event.toolName === "write") {
				const content = event.input.content as string;
				diffText = `📝 WRITE ${path}\n\n${content}`;
			} else if (event.toolName === "edit") {
				const content = event.input.content as string;
				const edits = event.input.edits as Array<{ oldText: string; newText: string }>;
				if (edits && edits.length > 0) {
					diffText = `📝 EDIT ${path}\n\n`;
					for (const edit of edits) {
						diffText += `---\n${edit.oldText}\n+++\n${edit.newText}\n\n`;
					}
				} else {
					diffText = `📝 EDIT ${path}\n\n${content}`;
				}
			}

			const approved = await ctx.ui.confirm(
				`Approve changes to ${path}?`,
				diffText,
			);

			if (!approved) {
				return {
					block: true,
					reason: `Edit blocked by user in accepts mode.`,
				};
			}

			// Remember approval for this path in this session
			if (!state.acceptedEdits) state.acceptedEdits = [];
			state.acceptedEdits.push(path);
		}
	});

	// ── Context injection for plan mode ──

	pi.on("before_agent_start", async (event) => {
		if (event.messageType !== "user") return;

		if (state.mode === "plan") {
			return {
				message: {
					customType: "mode-context",
					content: `[PLAN MODE ACTIVE]

You are in plan mode — read-only exploration.

Restrictions:
- edit and write tools are disabled
- bash is restricted to read-only commands (cat, grep, find, ls, git status/log/diff, etc.)
- Do NOT make any file changes or destructive operations

Create a detailed numbered plan under a "Plan:" header:

Plan:
1. First step
2. Second step
...

Ask clarifying questions if needed.`,
					display: false,
				},
			};
		}
	});

	// ── Session start: restore state ──

	pi.on("session_start", async (_event, ctx) => {
		const entries = ctx.sessionManager.getEntries();

		const modeEntry = entries
			.filter((e: { type: string; customType?: string }) => e.type === "custom" && e.customType === "mode-state")
			.pop() as { data?: ModeState } | undefined;

		if (modeEntry?.data) {
			state = modeEntry.data;
		}

		toolsBeforeMode = pi.getActiveTools();
		applyModeToTools(ctx);
		updateStatus(ctx);
	});
}
