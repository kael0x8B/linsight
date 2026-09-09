<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAccess } from "@vben/access";
import { useVbenDrawer } from "@vben/common-ui";
import {
  Alert,
  Button,
  Card,
  FormItem,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
  Textarea,
  message,
} from "ant-design-vue";
import { TableAction, useVbenVxeGrid } from "#/adapter/vxe-table";
import { getCameraPage, type AiVideoCameraApi } from "#/api/ai-video/camera";
import { getNodeSimpleList, type AiVideoNodeSimple } from "#/api/ai-video/node";
import {
  dryRunRule,
  getRuleVersions,
  publishRuleVersion,
  saveRuleVersion,
  validateRuleVersion,
  type AiVideoRuleApi,
  type RuleDetectionFrame,
} from "#/api/ai-video/rule";
import CameraPreviewPlayer from "#/components/ai-video/camera-preview-player.vue";
import { createRuleAst, cloneRuleAst } from "./rule-state";
const emit = defineEmits(["success"]);
const { hasAccessByCodes } = useAccess();
const canUpdate = computed(() => hasAccessByCodes(["ai-video:rule:update"]));
const canPublish = computed(() => hasAccessByCodes(["ai-video:rule:publish"]));
const canDryRun = computed(() => hasAccessByCodes(["ai-video:rule:dry-run"]));
const selected = ref<AiVideoRuleApi.Rule>();
const ast = ref(createRuleAst("AREA_INTRUSION"));
const versions = ref<AiVideoRuleApi.RuleVersion[]>([]);
const activeVersionId = ref<number>();
const savedJson = ref("");
const dirty = computed(() => JSON.stringify(ast.value) !== savedJson.value);
const regionIndex = ref(0);
const region = computed(() => ast.value.regions[regionIndex.value] ?? ast.value.regions[0]!);
const children = computed(() =>
  Array.isArray(ast.value.condition.children)
    ? (ast.value.condition.children as Record<string, unknown>[])
    : [],
);
const roi = computed(() =>
  children.value.find((c) => c.type === "ROI_ENTER" && c.regionId === region.value.id),
);
const nm = computed(() => children.value.find((c) => c.type === "N_OF_M"));
const duration = computed(() => children.value.find((c) => c.type === "DURATION"));
const objectClasses = computed({
  get: () => (Array.isArray(roi.value?.objectClasses) ? (roi.value.objectClasses as string[]) : []),
  set: (v: string[]) => {
    if (roi.value) roi.value.objectClasses = v;
  },
});
const special = computed(() =>
  children.value.find((c) => ["STATIONARY", "LOITERING"].includes(String(c.type))),
);
const mode = computed({
  get: () => String(special.value?.type ?? "ROI_ENTER"),
  set: (value: string) => {
    checkpoint();
    const nodes = children.value.filter(
      (c) => !["STATIONARY", "LOITERING"].includes(String(c.type)),
    );
    if (value === "STATIONARY") nodes.push({ type: value, maxMovement: 0.02 });
    if (value === "LOITERING") nodes.push({ type: value, minPathLength: 0.15, seconds: 30 });
    ast.value.condition.children = nodes;
  },
});
const simpleCondition = computed(
  () =>
    ast.value.condition.type === "AND" &&
    children.value.every((c) =>
      ["ROI_ENTER", "N_OF_M", "DURATION", "STATIONARY", "LOITERING"].includes(String(c.type)),
    ),
);
const undoStack = ref<AiVideoRuleApi.RuleAst[]>([]),
  redoStack = ref<AiVideoRuleApi.RuleAst[]>([]);
function checkpoint() {
  undoStack.value.push(cloneRuleAst(ast.value));
  if (undoStack.value.length > 30) undoStack.value.shift();
  redoStack.value = [];
}
function undo() {
  const a = undoStack.value.pop();
  if (a) {
    redoStack.value.push(cloneRuleAst(ast.value));
    ast.value = a;
  }
}
function redo() {
  const a = redoStack.value.pop();
  if (a) {
    undoStack.value.push(cloneRuleAst(ast.value));
    ast.value = a;
  }
}
const cameras = ref<AiVideoCameraApi.Camera[]>([]),
  nodes = ref<AiVideoNodeSimple[]>([]);
const cameraId = ref<number>(),
  nodeId = ref<number>(),
  preview = ref(false),
  background = ref("");
const player = ref<InstanceType<typeof CameraPreviewPlayer>>();
const camera = computed(() => cameras.value.find((c) => c.id === cameraId.value));
const sourceError = ref("");
const loadError = ref(""),
  saving = ref(false),
  trialBusy = ref(false),
  framesText = ref(""),
  trialResult = ref("");
const rawAst = ref(""),
  rawOpen = ref(false);
const polygon = computed(() =>
  region.value.points
    .map((p) => `${p.x * region.value.sourceWidth},${p.y * region.value.sourceHeight}`)
    .join(" "),
);
const dayOptions = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((label, i) => ({
  label,
  value: i + 1,
}));
const [Drawer, api] = useVbenDrawer({
  showConfirmButton: false,
  async onBeforeClose() {
    if (dirty.value) {
      message.warning("存在未保存修改，请保存，或点击“放弃修改并关闭”。");
      return false;
    }
  },
  onClosed() {
    preview.value = false;
  },
  async onOpenChange(open) {
    if (!open) {
      preview.value = false;
      return;
    }
    selected.value = api.getData<AiVideoRuleApi.Rule>();
    loadError.value = "";
    api.setState({ loading: true });
    try {
      versions.value = await getRuleVersions(selected.value!.id);
      const current =
        versions.value.find((v) => v.id === selected.value?.currentVersionId) ?? versions.value[0];
      loadVersion(current);
    } catch {
      loadError.value = "规则版本加载失败，请关闭后重试。";
    } finally {
      api.setState({ loading: false });
    }
    await loadSources();
  },
});
async function loadSources() {
  sourceError.value = "";
  async function allCameras() {
    const result: AiVideoCameraApi.Camera[] = [];
    for (let pageNo = 1; ; pageNo++) {
      const page = await getCameraPage({pageNo, pageSize:100});
      result.push(...page.list);
      if (result.length >= page.total || !page.list.length) return result;
    }
  }
  const results = await Promise.allSettled([allCameras(),getNodeSimpleList()]);
  if (results[0].status === "fulfilled") cameras.value = results[0].value;
  if (results[1].status === "fulfilled") nodes.value = results[1].value;
  if (results.some(result=>result.status === "rejected")) sourceError.value = "摄像头或节点目录读取失败，请检查查询权限后重试。";
  else if (!cameras.value.length || !nodes.value.length) sourceError.value = "尚无可用摄像头或节点，请先在对应中心完成配置。";
}
const [VersionGrid, versionGridApi] = useVbenVxeGrid<AiVideoRuleApi.RuleVersion>({
  gridOptions: {
    columns: [
      { field: "version", title: "版本", width: 65 },
      { field: "validationStatus", title: "状态", width: 105 },
      { field: "naturalSummary", title: "摘要", minWidth: 140 },
      { field: "actions", title: "操作", width: 120, slots: { default: "actions" } },
    ],
    pagerConfig: { enabled: false },
    rowConfig: { keyField: "id" },
    data: [],
  },
});
watch(versions, (v) => versionGridApi.setGridOptions({ data: v }));
watch(cameraId, () => {
  preview.value = false;
  background.value = "";
});
watch(nodeId, () => {
  preview.value = false;
});
function loadVersion(v?: AiVideoRuleApi.RuleVersion) {
  ast.value = v ? cloneRuleAst(v.ast) : createRuleAst(selected.value!.eventType);
  activeVersionId.value = v?.id;
  regionIndex.value = 0;
  savedJson.value = JSON.stringify(ast.value);
  undoStack.value = [];
  redoStack.value = [];
  trialResult.value = "";
  rawOpen.value = false;
}
function editVersion(v: AiVideoRuleApi.RuleVersion) {
  if (dirty.value) {
    message.warning("请先保存修改，或放弃修改后再载入版本");
    return;
  }
  loadVersion(v);
}
function addPoint(e: MouseEvent) {
  if (!canUpdate.value || region.value.points.length >= 20) return;
  const r = (e.currentTarget as SVGElement).getBoundingClientRect();
  checkpoint();
  region.value.points.push({
    x: +((e.clientX - r.left) / r.width).toFixed(4),
    y: +((e.clientY - r.top) / r.height).toFixed(4),
  });
}
function removePoint(i: number) {
  if (region.value.points.length <= 3) {
    message.warning("多边形至少保留三个点");
    return;
  }
  checkpoint();
  region.value.points.splice(i, 1);
}
function fullFrame() {
  checkpoint();
  region.value.points = [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
    { x: 0, y: 1 },
  ];
}
function capture() {
  const image = player.value?.captureFrame();
  if (!image) {
    message.warning("请等待视频开始播放后再截取");
    return;
  }
  checkpoint();
  background.value = image.dataUrl;
  region.value.sourceWidth = image.width;
  region.value.sourceHeight = image.height;
  preview.value = false;
}
async function save() {
  if (!selected.value) return;
  if (
    ast.value.schedule.weekly.some(
      (w) =>
        !w.days.length ||
        !/^\d{2}:\d{2}$/.test(w.start) ||
        !/^\d{2}:\d{2}$/.test(w.end) ||
        w.start > w.end,
    )
  ) {
    message.warning("请填写有效时段；跨午夜请拆成两个时段");
    return;
  }
  saving.value = true;
  try {
    ast.value.eventType = selected.value.eventType;
    const id = await saveRuleVersion(selected.value.id, ast.value);
    const errors = await validateRuleVersion(id);
    versions.value = await getRuleVersions(selected.value.id);
    activeVersionId.value = id;
    savedJson.value = JSON.stringify(ast.value);
    message[errors.length ? "warning" : "success"](
      errors.length ? errors.join("；") : "新版本校验通过，可以发布",
    );
  } finally {
    saving.value = false;
  }
}
async function publish(v: AiVideoRuleApi.RuleVersion) {
  await publishRuleVersion(v.id);
  versions.value = await getRuleVersions(selected.value!.id);
  emit("success");
  message.success(`v${v.version} 已发布，请在任务中心选择此版本`);
}
async function trial() {
  if (dirty.value || !activeVersionId.value) {
    message.warning("请先保存当前修改，试算按保存的版本执行");
    return;
  }
  if (!nodeId.value || !cameraId.value) {
    message.warning("请先选择执行节点和摄像头");
    return;
  }
  try {
    const frames = JSON.parse(framesText.value) as RuleDetectionFrame[];
    if (!Array.isArray(frames) || frames.length < 1 || frames.length > 300)
      throw new Error("请输入 1–300 帧检测结果数组");
    trialBusy.value = true;
    trialResult.value = "";
    const result = await dryRunRule(activeVersionId.value, nodeId.value, cameraId.value, frames);
    trialResult.value = `${result.confirmed ? "满足告警条件" : "未满足告警条件"}；状态：${result.transitions.map((t) => t.state).join(" → ") || "无状态变化"}`;
  } catch (e) {
    trialResult.value = e instanceof Error ? e.message : "试算失败，请检查检测序列和节点版本";
  } finally {
    trialBusy.value = false;
  }
}
async function importFrames(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (file.size > 56 * 1024) {
    message.warning("检测序列最大 56 KB");
    return;
  }
  framesText.value = await file.text();
}
function editRaw() {
  rawAst.value = JSON.stringify(ast.value, null, 2);
  rawOpen.value = true;
}
function applyRaw() {
  try {
    const v = JSON.parse(rawAst.value) as AiVideoRuleApi.RuleAst;
    if (
      !Array.isArray(v.regions) ||
      !v.regions.length ||
      v.regions.some(
        (r) =>
          !Array.isArray(r.points) ||
          r.points.length < 3 ||
          !Number.isFinite(r.sourceWidth) ||
          r.sourceWidth <= 0 ||
          !Number.isFinite(r.sourceHeight) ||
          r.sourceHeight <= 0 ||
          r.points.some((p) => !Number.isFinite(p.x) || !Number.isFinite(p.y)),
      ) ||
      !v.condition ||
      !Array.isArray(v.schedule?.weekly) ||
      !v.schedule.weekly.length ||
      v.schedule.weekly.some(
        (w) => !Array.isArray(w.days) || typeof w.start !== "string" || typeof w.end !== "string",
      ) ||
      !v.dedup
    )
      throw new Error();
    checkpoint();
    ast.value = v;
    ast.value.eventType = selected.value!.eventType;
    regionIndex.value = 0;
    rawOpen.value = false;
  } catch {
    message.warning("AST 格式不正确，需包含区域、条件、时间表和去重配置");
  }
}
function discard() {
  savedJson.value = JSON.stringify(ast.value);
  void api.close();
}
</script>
<template>
  <Drawer class="w-[96vw]" :title="`${selected?.name ?? '规则'} · 区域与告警条件`">
    <Alert v-if="loadError" :message="loadError" type="error" show-icon />
    <div v-else class="grid grid-cols-12 gap-4">
      <div class="col-span-12 min-w-0 space-y-3 xl:col-span-3">
        <Card size="small" title="画面来源">
          <Alert v-if="sourceError" :message="sourceError" type="warning" show-icon><template #action><Button @click="loadSources">重试</Button></template></Alert>
          <FormItem label="摄像头"
            ><Select
              v-model:value="cameraId"
              class="w-full"
              show-search
              option-filter-prop="label"
              :options="cameras.map((c) => ({ label: c.name, value: c.id }))"
              placeholder="选择摄像头"
          /></FormItem>
          <FormItem label="执行节点"
            ><Select
              v-model:value="nodeId"
              class="w-full"
              :options="nodes.map((n) => ({ label: n.name, value: n.id }))"
              placeholder="选择在线节点"
          /></FormItem>
          <Button :disabled="!camera || !nodeId" @click="preview = !preview">{{
            preview ? "关闭预览" : "打开预览"
          }}</Button>
          <p class="mt-2 text-xs text-muted-foreground">
            截图只用于本次画区域；请确认区域与任务摄像头视角一致。
          </p>
        </Card>
        <Card size="small" title="区域与顶点">
          <Select
            v-model:value="regionIndex"
            class="mb-3 w-full"
            :options="ast.regions.map((r, i) => ({ label: r.name, value: i }))"
          />
          <div v-for="(p, i) in region.points" :key="i" class="mb-2 flex items-center gap-1">
            <span>{{ i + 1 }}</span
            ><InputNumber
              v-model:value="p.x"
              class="min-w-0 flex-1"
              :min="0"
              :max="1"
              :step="0.01"
              :disabled="!canUpdate"
              @focus="checkpoint"
            />
            <InputNumber
              v-model:value="p.y"
              class="min-w-0 flex-1"
              :min="0"
              :max="1"
              :step="0.01"
              :disabled="!canUpdate"
              @focus="checkpoint"
            />
            <Button v-if="canUpdate" type="text" danger @click="removePoint(i)">×</Button>
          </div>
        </Card>
      </div>
      <div class="col-span-12 min-w-0 space-y-3 xl:col-span-5">
        <Card v-if="preview && camera && nodeId" size="small" title="实时画面"
          ><CameraPreviewPlayer
            ref="player"
            :camera="camera"
            :node-id="nodeId"
            :overlay-enabled="false"
          /><Button class="mt-2" @click="capture">截取画面用于绘制</Button></Card
        >
        <Card size="small" title="区域画布">
          <Space class="mb-3"
            ><Button :disabled="!canUpdate" @click="fullFrame">全画面</Button
            ><Button :disabled="!undoStack.length" @click="undo">撤销</Button
            ><Button :disabled="!redoStack.length" @click="redo">重做</Button></Space
          >
          <svg
            class="w-full cursor-crosshair rounded bg-slate-900"
            :style="{ aspectRatio: `${region.sourceWidth}/${region.sourceHeight}` }"
            :viewBox="`0 0 ${region.sourceWidth} ${region.sourceHeight}`"
            @click="addPoint"
          >
            <image
              v-if="background"
              :href="background"
              width="100%"
              height="100%"
              preserveAspectRatio="none"
            />
            <polygon
              :points="polygon"
              fill="#38bdf833"
              stroke="#38bdf8"
              stroke-width="3"
              vector-effect="non-scaling-stroke"
            />
            <circle
              v-for="(p, i) in region.points"
              :key="i"
              :cx="p.x * region.sourceWidth"
              :cy="p.y * region.sourceHeight"
              :r="region.sourceWidth / 160"
              fill="white"
            />
          </svg>
          <p class="mt-2 text-xs text-muted-foreground">
            {{
              background ? "已载入摄像头截图" : "未载入截图，可先打开预览并截取画面"
            }}。点击添加顶点，左侧调整归一化坐标。{{ region.sourceWidth }} ×
            {{ region.sourceHeight }}
          </p>
        </Card>
        <Card size="small" title="规则版本">
          <VersionGrid
            ><template #actions="{ row }"
              ><TableAction
                :actions="[
                  { label: '载入', onClick: () => editVersion(row) },
                  {
                    label: '发布',
                    ifShow: canPublish && row.validationStatus === 'VALID',
                    onClick: () => publish(row),
                  },
                ]" /></template
          ></VersionGrid>
        </Card>
        <Card v-if="canDryRun" size="small" title="检测序列试算">
          <Alert
            message="导入算法筛选后的告警候选序列 JSON（最多 300 帧、56 KB），在所选节点规则引擎中试算，不写入告警。时间戳使用实际毫秒时间，受规则时段限制；不对模型原始输出再次判断穿戴状态。"
            type="info"
            show-icon
          />
          <input class="my-2" type="file" accept="application/json,.json" @change="importFrames" />
          <Textarea
            v-model:value="framesText"
            :rows="5"
            placeholder='[{"timestampMillis":实际时间戳,"objects":[{"class":"person","confidence":0.9,"trackId":"1","bbox":{"x":0.4,"y":0.3,"width":0.1,"height":0.2}}]}]'
          />
          <Button class="mt-2" :loading="trialBusy" @click="trial">试算当前保存版本</Button>
          <Alert v-if="trialResult" class="mt-2" :message="trialResult" type="info" show-icon />
        </Card>
      </div>
      <div class="col-span-12 min-w-0 space-y-3 xl:col-span-4" @focusin="checkpoint">
        <Card size="small" title="告警条件">
          <Tag>{{ ast.eventType }}</Tag
          ><Tag>{{ dirty ? "有未保存修改" : `版本 #${activeVersionId ?? "未保存"}` }}</Tag>
          <Alert
            v-if="!simpleCondition"
            class="my-2"
            message="此版本包含复合条件，请通过下方高级 AST 编辑；保存时保留完整条件树。"
            type="info"
          />
          <FormItem label="区域名称"
            ><Input v-model:value="region.name" :disabled="!canUpdate"
          /></FormItem>
          <FormItem v-if="roi" label="目标类别"
            ><Select
              v-model:value="objectClasses"
              mode="tags"
              :disabled="!canUpdate"
              :options="[
                { label: '人员 person', value: 'person' },
                { label: '车辆 car', value: 'car' },
              ]"
          /></FormItem>
          <p class="mb-2 text-xs text-muted-foreground">
            安全帽、反光衣算法已经筛选出违规人员，规则通常选择 person。
          </p>
          <div class="grid grid-cols-2 gap-x-3">
            <FormItem v-if="simpleCondition" label="场景判定"
              ><Select
                v-model:value="mode"
                :disabled="!canUpdate"
                :options="[
                  { label: '进入区域', value: 'ROI_ENTER' },
                  { label: '静止/违停', value: 'STATIONARY' },
                  { label: '区域徘徊', value: 'LOITERING' },
                ]"
            /></FormItem>
            <FormItem v-if="special?.type === 'STATIONARY'" label="最大移动幅度"
              ><InputNumber
                :value="Number(special.maxMovement)"
                :min="0.001"
                :max="1"
                :step="0.01"
                :disabled="!canUpdate"
                @update:value="(v) => special && (special.maxMovement = v)"
            /></FormItem>
            <FormItem v-if="special?.type === 'LOITERING'" label="观察秒数"
              ><InputNumber
                :value="Number(special.seconds)"
                :min="1"
                :disabled="!canUpdate"
                @update:value="(v) => special && (special.seconds = v)"
            /></FormItem>
            <FormItem v-if="special?.type === 'LOITERING'" label="最小累计移动"
              ><InputNumber
                :value="Number(special.minPathLength)"
                :min="0.001"
                :max="1"
                :step="0.01"
                :disabled="!canUpdate"
                @update:value="(v) => special && (special.minPathLength = v)"
            /></FormItem>
            <FormItem label="判定方式"
              ><Select
                v-model:value="region.pointMode"
                :disabled="!canUpdate"
                :options="[
                  { label: '脚点', value: 'FOOT' },
                  { label: '中心点', value: 'CENTROID' },
                  { label: '重叠率', value: 'OVERLAP' },
                ]"
            /></FormItem>
            <FormItem v-if="region.pointMode === 'OVERLAP'" label="最小重叠率"
              ><InputNumber
                v-model:value="region.overlapThreshold"
                :disabled="!canUpdate"
                :min="0.01"
                :max="1"
                :step="0.05"
            /></FormItem>
            <FormItem v-if="nm" label="命中 N 帧"
              ><InputNumber
                :value="Number(nm.n)"
                :disabled="!canUpdate"
                :min="1"
                :max="Number(nm.m)"
                @update:value="(v) => nm && (nm.n = v)"
            /></FormItem>
            <FormItem v-if="nm" label="观察 M 帧"
              ><InputNumber
                :value="Number(nm.m)"
                :disabled="!canUpdate"
                :min="Number(nm.n)"
                :max="300"
                @update:value="(v) => nm && (nm.m = v)"
            /></FormItem>
            <FormItem v-if="duration" label="持续秒数"
              ><InputNumber
                :value="Number(duration.seconds)"
                :disabled="!canUpdate"
                :min="0"
                @update:value="(v) => duration && (duration.seconds = v)"
            /></FormItem>
            <FormItem label="告警等级"
              ><Select
                v-model:value="ast.severity"
                :disabled="!canUpdate"
                :options="
                  ['INFO', 'MINOR', 'MAJOR', 'CRITICAL'].map((value) => ({ value, label: value }))
                "
            /></FormItem>
            <FormItem label="冷却秒数"
              ><InputNumber v-model:value="ast.cooldownSeconds" :disabled="!canUpdate" :min="0"
            /></FormItem>
            <FormItem label="恢复秒数"
              ><InputNumber v-model:value="ast.recoverySeconds" :disabled="!canUpdate" :min="0"
            /></FormItem>
            <FormItem label="去重范围"
              ><Select
                v-model:value="ast.dedup.scope"
                :disabled="!canUpdate"
                :options="[
                  { label: '同一目标', value: 'TRACK' },
                  { label: '同摄像头任务', value: 'CAMERA_TASK_TYPE' },
                ]"
            /></FormItem>
            <FormItem label="去重秒数"
              ><InputNumber v-model:value="ast.dedup.windowSeconds" :disabled="!canUpdate" :min="1"
            /></FormItem>
          </div>
        </Card>
        <Card size="small" title="生效时间">
          <FormItem label="时区"
            ><Input v-model:value="ast.schedule.timezone" :disabled="!canUpdate"
          /></FormItem>
          <div v-for="(w, i) in ast.schedule.weekly" :key="i" class="mb-3 rounded border p-2">
            <Select
              v-model:value="w.days"
              mode="multiple"
              class="mb-2 w-full"
              :disabled="!canUpdate"
              :options="dayOptions"
            />
            <div class="flex items-center gap-2">
              <Input v-model:value="w.start" type="time" :disabled="!canUpdate" /><span>至</span
              ><Input v-model:value="w.end" type="time" :disabled="!canUpdate" /><Button
                v-if="canUpdate && ast.schedule.weekly.length > 1"
                danger
                @click="ast.schedule.weekly.splice(i, 1)"
                >删除</Button
              >
            </div>
          </div>
          <Button
            v-if="canUpdate"
            @click="
              ast.schedule.weekly.push({ days: [1, 2, 3, 4, 5], start: '08:00', end: '18:00' })
            "
            >添加时段</Button
          >
          <p class="mt-2 text-xs text-muted-foreground">跨午夜请拆成两个时段，并分别选择星期。</p>
        </Card>
        <Space
          ><Button v-if="canUpdate" type="primary" :loading="saving" @click="save"
            >校验并保存新版本</Button
          ><Button @click="editRaw">高级 AST</Button></Space
        >
        <Card v-if="rawOpen" size="small" title="完整规则 AST"
          ><Textarea v-model:value="rawAst" :rows="16" :disabled="!canUpdate" /><Button
            v-if="canUpdate"
            class="mt-2"
            @click="applyRaw"
            >应用到编辑器</Button
          ></Card
        >
      </div>
    </div>
    <template #extra><Button @click="discard">放弃修改并关闭</Button></template>
  </Drawer>
</template>
