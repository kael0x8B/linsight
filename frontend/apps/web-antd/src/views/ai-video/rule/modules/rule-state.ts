import type { AiVideoRuleApi } from "#/api/ai-video/rule";
export function createRuleAst(eventType: string): AiVideoRuleApi.RuleAst {
  return {
    schemaVersion: "1.0",
    eventType,
    severity: "MAJOR",
    cooldownSeconds: 30,
    recoverySeconds: 5,
    dedup: { scope: "TRACK", windowSeconds: 30 },
    schedule: {
      timezone: "Asia/Shanghai",
      weekly: [{ days: [1, 2, 3, 4, 5, 6, 7], start: "00:00", end: "23:59" }],
    },
    regions: [
      {
        id: "main",
        name: "主区域",
        type: "POLYGON",
        pointMode: "FOOT",
        overlapThreshold: 0.2,
        sourceWidth: 1920,
        sourceHeight: 1080,
        points: [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
          { x: 1, y: 1 },
          { x: 0, y: 1 },
        ],
      },
    ],
    condition: {
      type: "AND",
      children: [
        { type: "ROI_ENTER", regionId: "main", objectClasses: ["person"] },
        { type: "N_OF_M", n: 3, m: 5 },
        { type: "DURATION", seconds: 2 },
      ],
    },
  };
}
export function cloneRuleAst(ast: AiVideoRuleApi.RuleAst): AiVideoRuleApi.RuleAst {
  return JSON.parse(JSON.stringify(ast));
}
