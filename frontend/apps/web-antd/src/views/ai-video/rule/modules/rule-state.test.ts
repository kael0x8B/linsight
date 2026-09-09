import { describe, expect, it } from "vitest";
import { reactive } from "vue";
import { createRuleAst, cloneRuleAst } from "./rule-state";
describe("rule editor versions", () => {
  it("uses the selected event type for the first version", () => {
    expect(createRuleAst("REFLECTIVE_VEST").eventType).toBe("REFLECTIVE_VEST");
    expect(createRuleAst("SAFETY_HELMET").eventType).toBe("SAFETY_HELMET");
  });
  it("retains compound conditions when copying a reactive version", () => {
    const ast = reactive(createRuleAst("REFLECTIVE_VEST"));
    ast.condition = {
      type: "OR",
      children: [
        { type: "COUNT_BELOW", regionId: "main", objectClasses: ["person"], minCount: 1 },
        { type: "NOT", child: { type: "ROI_ENTER", regionId: "main", objectClasses: ["car"] } },
      ],
    };
    const copy = cloneRuleAst(ast);
    expect(copy.condition).toEqual(ast.condition);
    copy.regions[0]!.points[0]!.x = 0.3;
    expect(ast.regions[0]!.points[0]!.x).toBe(0);
  });
});
