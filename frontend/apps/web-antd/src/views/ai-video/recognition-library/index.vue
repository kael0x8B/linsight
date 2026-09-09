<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoRecognitionLibraryApi } from '#/api/ai-video/recognition-library';

import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, Page, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Empty,
  Input,
  Pagination,
  Segmented,
  Select,
  Spin,
  Statistic,
  TabPane,
  Tabs,
  Tag,
} from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteRecognitionEntry,
  deleteRecognitionLibrary,
  getRecognitionEntryPage,
  getRecognitionLibraryPage,
} from '#/api/ai-video/recognition-library';
import { AiPageHeader } from '#/components/ai-video';
import { $t } from '#/locales';
import { router } from '#/router';

import { entryColumns, entrySearchSchema } from './data';
import EntryAccessModal from './modules/entry-access-modal.vue';
import EntryForm from './modules/entry-form.vue';
import { extractionState } from './modules/extraction-state';
import FaceVerificationModal from './modules/face-verification-modal.vue';
import LibraryForm from './modules/library-form.vue';
const [EntryAccess, entryAccessApi] = useVbenModal({connectedComponent:EntryAccessModal,destroyOnClose:true});

const [FaceVerification, faceVerificationApi] = useVbenModal({ connectedComponent: FaceVerificationModal });

type EntryViewMode = 'CARD' | 'LIST';

const { hasAccessByCodes } = useAccess();
const canCreate = computed(() => hasAccessByCodes(['ai-video:library:create']));
const canUpdate = computed(() => hasAccessByCodes(['ai-video:library:update']));
const canExtract = computed(() => canUpdate.value && hasAccessByCodes(['ai-video:model:test']));
const canDelete = computed(() => hasAccessByCodes(['ai-video:library:delete']));

const activeType = ref<AiVideoRecognitionLibraryApi.LibraryType>('FACE');
const selectedLibrary = ref<AiVideoRecognitionLibraryApi.Library>();
const libraries = ref<AiVideoRecognitionLibraryApi.Library[]>([]);
const libraryTotal = ref(0);
const libraryLoading = ref(false);
const loadError = ref('');
const libraryQuery = reactive<{
  name: string;
  pageNo: number;
  pageSize: number;
  status?: number;
}>({ name: '', pageNo: 1, pageSize: 8, status: undefined });

const entryViewMode = ref<EntryViewMode>('CARD');
const entryCards = ref<AiVideoRecognitionLibraryApi.Entry[]>([]);
const entryTotal = ref(0);
const entryLoading = ref(false);
const entryQuery = reactive<{
  featureStatus?: string;
  name: string;
  pageNo: number;
  pageSize: number;
}>({ featureStatus: undefined, name: '', pageNo: 1, pageSize: 12 });

const displayLibrary = computed(
  () => selectedLibrary.value ?? libraries.value.find(library => library.status === 0) ?? libraries.value[0],
);

const typeMeta = computed(
  () =>
    ({
      FACE: {
        description: '这里管理人员照片和参考库；在边缘盒子中配置、启停主动刷脸。',
        dimension: displayLibrary.value?.featureDimension
          ? `${displayLibrary.value.featureDimension} 维`
          : '待配置',
        icon: 'lucide:scan-face',
        libraryLabel: '人脸库',
        mode: '1:N 比对',
        title: '人脸特征识别',
      },
      PLATE: {
        description: '内部车辆、访客车辆和重点车辆的车牌精确匹配参考库。',
        dimension: '结构化字符',
        icon: 'lucide:car-front',
        libraryLabel: '车牌库',
        mode: '精确匹配',
        title: '车牌识别匹配',
      },
      POSE: {
        description: '按场景维护跌倒、攀爬、睡岗等姿态与风险分类参考样本。',
        dimension: '关键点/时序',
        icon: 'lucide:person-standing',
        libraryLabel: '场景姿态库',
        mode: '姿态分类',
        title: '场景姿态识别',
      },
    })[activeType.value],
);

const externalCodeTitles = {
  FACE: '工号/人员编号',
  PLATE: '车牌号码',
  POSE: '姿态编码',
} as const;
const externalCodeTitle = computed(() => externalCodeTitles[activeType.value]);

const [LibraryModal, libraryModalApi] = useVbenModal({
  connectedComponent: LibraryForm,
  destroyOnClose: true,
});
const [EntryModal, entryModalApi] = useVbenModal({
  connectedComponent: EntryForm,
  destroyOnClose: true,
});

const [EntryGrid, entryGridApi] = useVbenVxeGrid({
  formOptions: { schema: entrySearchSchema(), submitOnChange: true },
  gridOptions: {
    columns: entryColumns('FACE'),
    height: 360,
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) =>
          selectedLibrary.value
            ? getRecognitionEntryPage({
                ...values,
                libraryId: selectedLibrary.value.id,
                pageNo: page.currentPage,
                pageSize: page.pageSize,
              })
            : { list: [], total: 0 },
      },
    },
    rowConfig: { isHover: true, keyField: 'id' },
    toolbarConfig: { refresh: true, search: true },
  } as VxeTableGridOptions<AiVideoRecognitionLibraryApi.Entry>,
});

async function loadLibraries() {
  libraryLoading.value = true;
  loadError.value = '';
  try {
    const result = await getRecognitionLibraryPage({
      libraryType: activeType.value,
      name: libraryQuery.name || undefined,
      pageNo: libraryQuery.pageNo,
      pageSize: libraryQuery.pageSize,
      status: libraryQuery.status,
    });
    libraries.value = result.list;
    libraryTotal.value = result.total;
    if (selectedLibrary.value) {
      const refreshed = result.list.find(
        (item) => item.id === selectedLibrary.value?.id,
      );
      if (refreshed) selectedLibrary.value = refreshed;
    }
  } catch {
    loadError.value = '识别参考库加载失败，请检查数据库迁移和控制面服务。';
  } finally {
    libraryLoading.value = false;
  }
}

async function loadEntryCards() {
  if (!selectedLibrary.value) {
    entryCards.value = [];
    entryTotal.value = 0;
    return;
  }
  entryLoading.value = true;
  try {
    const result = await getRecognitionEntryPage({
      featureStatus: entryQuery.featureStatus,
      libraryId: selectedLibrary.value.id,
      name: entryQuery.name || undefined,
      pageNo: entryQuery.pageNo,
      pageSize: entryQuery.pageSize,
    });
    entryCards.value = result.list;
    entryTotal.value = result.total;
  } finally {
    entryLoading.value = false;
  }
}

async function changeType() {
  selectedLibrary.value = undefined;
  libraryQuery.name = '';
  libraryQuery.status = undefined;
  libraryQuery.pageNo = 1;
  entryGridApi.setGridOptions({ columns: entryColumns(activeType.value) });
  await loadLibraries();
}

async function searchLibraries() {
  libraryQuery.pageNo = 1;
  await loadLibraries();
}

async function resetLibrarySearch() {
  libraryQuery.name = '';
  libraryQuery.status = undefined;
  await searchLibraries();
}

async function changeLibraryPage(pageNo: number, pageSize: number) {
  libraryQuery.pageNo = pageNo;
  libraryQuery.pageSize = pageSize;
  await loadLibraries();
}

function openCreateLibrary() {
  libraryModalApi.setData({ libraryType: activeType.value }).open();
}

function openEditLibrary(item: AiVideoRecognitionLibraryApi.Library) {
  libraryModalApi.setData({ item, libraryType: activeType.value }).open();
}

async function chooseLibrary(item: AiVideoRecognitionLibraryApi.Library) {
  selectedLibrary.value = item;
  entryViewMode.value = 'CARD';
  Object.assign(entryQuery, {
    featureStatus: undefined,
    name: '',
    pageNo: 1,
  });
  await loadEntryCards();
}

function leaveLibrary() {
  selectedLibrary.value = undefined;
  entryCards.value = [];
  entryTotal.value = 0;
}

async function removeLibrary(item: AiVideoRecognitionLibraryApi.Library) {
  await confirm(`确认删除参考库“${item.name}”吗？只有空库允许删除。`);
  await deleteRecognitionLibrary(item.id);
  if (selectedLibrary.value?.id === item.id) leaveLibrary();
  await loadLibraries();
}

function manageRecognitionEngine() {
  if (displayLibrary.value) openEditLibrary(displayLibrary.value);
}

function goModelCenter() {
  void router.push({ path: '/ai-video/model' });
}

function openCreateEntry() {
  if (!selectedLibrary.value) return;
  entryModalApi
    .setData({
      libraryId: selectedLibrary.value.id,
      libraryType: activeType.value,
    })
    .open();
}

function openExtractEntry(item: AiVideoRecognitionLibraryApi.Entry) {
  entryAccessApi.setData({enrollmentOnly:true,libraryId:item.libraryId,entry:item}).open();
}
function openEditEntry(item: AiVideoRecognitionLibraryApi.Entry) {
  entryModalApi
    .setData({
      item,
      libraryId: item.libraryId,
      libraryType: activeType.value,
    })
    .open();
}

async function removeEntry(item: AiVideoRecognitionLibraryApi.Entry) {
  await confirm(
    `确认删除参考条目“${item.name}”吗？已生成的历史事件不会被修改。`,
  );
  await deleteRecognitionEntry(item.id);
  await refreshEntries();
}

async function refreshEntries() {
  await Promise.all([loadLibraries(), loadEntryCards()]);
  if (entryViewMode.value === 'LIST') await entryGridApi.query();
}

async function changeEntryView(value: number | string) {
  entryViewMode.value = value as EntryViewMode;
  await nextTick();
  await (entryViewMode.value === 'LIST'
    ? entryGridApi.query()
    : loadEntryCards());
}

async function searchEntries() {
  entryQuery.pageNo = 1;
  await loadEntryCards();
}

async function resetEntrySearch() {
  entryQuery.name = '';
  entryQuery.featureStatus = undefined;
  await searchEntries();
}

async function changeEntryPage(pageNo: number, pageSize: number) {
  entryQuery.pageNo = pageNo;
  entryQuery.pageSize = pageSize;
  await loadEntryCards();
}

function attributeText(item: AiVideoRecognitionLibraryApi.Entry) {
  const values = Object.entries(item.attributes)
    .filter(([key, value]) => ['category','department','description','riskLevel'].includes(key) && value)
    .slice(0, 3)
    .map(([key, value]) => key==='riskLevel' ? ({NORMAL:'普通',WATCH:'关注',HIGH:'高风险'}[String(value)]??String(value)) : String(value));
  return values.join(' · ') || '暂无业务属性';
}

function featureStatusText(status: string) {
  return (
    { FAILED: '提取失败', PENDING: '待提取', READY: '已就绪' }[status] ?? status
  );
}

function featureStatusColor(status: string) {
  return { FAILED: 'error', PENDING: 'processing', READY: 'success' }[status];
}

let extractionTimer:ReturnType<typeof setInterval>|undefined;
onMounted(()=>{void loadLibraries();extractionTimer=setInterval(()=>{
  if(!entryLoading.value && entryCards.value.some(v=>extractionState(v).processing)) void loadEntryCards().catch(()=>{});
},3000);});
onBeforeUnmount(()=>{if(extractionTimer)clearInterval(extractionTimer);});
</script>

<template>
  <Page auto-content-height>
    <LibraryModal @success="loadLibraries" />
    <EntryModal @success="refreshEntries" />
    <div class="ai-page ai-page-stack recognition-page">
      <AiPageHeader
        title="识别参考库"
        description="统一管理人脸、车牌和场景姿态样本，供算法任务动态绑定，不为每种识别能力新建页面。"
        icon="lucide:library-big"
        status="Recognition Assets"
      >
        <template #extra>
          <Button v-if="canCreate" type="primary" @click="openCreateLibrary">
            <IconifyIcon icon="lucide:plus" />新增{{ typeMeta.libraryLabel }}
          </Button>
        </template>
      </AiPageHeader>

      <Alert v-if="loadError" :message="loadError" show-icon type="error" />
      <Tabs
        v-model:active-key="activeType"
        class="recognition-tabs"
        @change="changeType"
      >
        <TabPane key="FACE" tab="人脸库" />
        <TabPane key="PLATE" tab="车牌库" />
        <TabPane key="POSE" tab="场景姿态库" />
      </Tabs>

      <Card class="engine-card" :bordered="false">
        <div class="engine-main">
          <div class="engine-heading">
            <Avatar :size="48" shape="square">
              <IconifyIcon :icon="typeMeta.icon" class="text-2xl" />
            </Avatar>
            <div class="min-w-0">
              <div class="engine-heading__title">
                <h2>{{ typeMeta.title }}</h2>
                <Tag
                  :color="
                    displayLibrary?.engineModelVersionId ? 'success' : 'blue'
                  "
                >
                  {{
                    displayLibrary?.engineModelVersionId
                      ? '已绑定模型，效果待核验'
                      : '待配置引擎'
                  }}
                </Tag>
              </div>
              <p>{{ typeMeta.description }}</p>
            </div>
          </div>
          <div class="engine-statistics">
            <Statistic
              title="当前参考库"
              :value="displayLibrary?.name ?? '暂无参考库'"
            />
            <Statistic title="特征/数据形式" :value="typeMeta.dimension" />
            <Statistic title="匹配模式" :value="typeMeta.mode" />
            <Statistic
              title="参考条目"
              :value="displayLibrary?.entryCount ?? 0"
            />
          </div>
        </div>
        <div class="engine-action">
          <div class="engine-action__status">
            <span class="engine-action__icon-wrap">
              <IconifyIcon
                :icon="
                  displayLibrary?.engineModelVersionId
                    ? 'lucide:badge-check'
                    : 'lucide:cloud-download'
                "
                class="engine-action__icon"
              />
            </span>
            <div>
              <strong>
                {{
                  displayLibrary?.engineModelVersionId
                    ? `模型版本 #${displayLibrary.engineModelVersionId}`
                    : '尚未绑定可执行模型'
                }}
              </strong>
              <span>
                {{
                  displayLibrary?.engineModelVersionId
                    ? '绑定记录不代表特征提取、身份比对或活体校验已经通过。'
                    : '请先部署适用的核验模型并完成测试。'
                }}
              </span>
            </div>
          </div>
          <div class="engine-action__note">
            引擎绑定属于当前识别库；模型发布和节点部署仍由模型中心统一管理。
          </div>
          <div class="engine-action__buttons">
            <Button
              :disabled="!displayLibrary || !canUpdate"
              type="primary"
              @click="manageRecognitionEngine"
            >
              管理识别引擎
            </Button>
            <Button @click="goModelCenter">模型中心</Button>
            <Button v-if="activeType === 'FACE' && hasAccessByCodes(['ai-video:task:query']) && hasAccessByCodes(['ai-video:library:query'])" type="primary" @click="entryAccessApi.setData({enrollmentOnly:true,libraryId:displayLibrary?.id}).open()">{{ $t('entry-access.enrollTab') }}</Button>
            <Button v-if="activeType === 'FACE' && hasAccessByCodes(['ai-video:model:test', 'ai-video:camera:query'])" @click="faceVerificationApi.open()">单次比对诊断（1:1）</Button>
          </div>
        </div>
      </Card>

      <Card v-if="!selectedLibrary" class="library-browser">
        <template #title>
          <div class="section-heading">
            <span>{{ typeMeta.libraryLabel }}</span>
            <Tag>{{ libraryTotal }} 个库</Tag>
          </div>
        </template>
        <div class="filter-bar">
          <label class="filter-field filter-field--wide">
            <span>库名称</span>
            <Input
              v-model:value="libraryQuery.name"
              allow-clear
              placeholder="请输入库名称"
              @press-enter="searchLibraries"
            />
          </label>
          <label class="filter-field">
            <span>状态</span>
            <Select
              v-model:value="libraryQuery.status"
              allow-clear
              :options="[
                { label: '启用', value: 0 },
                { label: '停用', value: 1 },
              ]"
              placeholder="请选择"
            />
          </label>
          <div class="filter-actions">
            <Button @click="resetLibrarySearch">重置</Button>
            <Button type="primary" @click="searchLibraries">搜索</Button>
          </div>
        </div>

        <Spin :spinning="libraryLoading">
          <div v-if="libraries.length" class="library-card-grid">
            <article
              v-for="item in libraries"
              :key="item.id"
              class="library-card"
              role="button"
              tabindex="0"
              :aria-label="`进入${item.name}`"
              @click="chooseLibrary(item)"
              @keydown.enter="chooseLibrary(item)"
            >
              <div class="library-card__header">
                <span class="library-card__icon"><IconifyIcon :icon="typeMeta.icon" /></span>
                <Badge
                  :status="item.status === 0 ? 'success' : 'default'"
                  :text="item.status === 0 ? '启用' : '停用'"
                />
              </div>
              <div>
                <h3>{{ item.name }}</h3>
                <code>{{ item.code }}</code>
              </div>
              <p>{{ item.description || '尚未填写参考库说明。' }}</p>
              <div class="library-card__metrics">
                <div>
                  <strong>{{ item.entryCount }}</strong><span>参考条目</span>
                </div>
                <div>
                  <strong>{{
                    item.engineModelVersionId
                      ? `#${item.engineModelVersionId}`
                      : '待配置'
                  }}</strong>
                  <span>识别引擎</span>
                </div>
              </div>
              <div class="library-card__footer" @click.stop>
                <span>点击卡片进入内容</span>
                <div>
                  <Button
                    v-if="canUpdate"
                    size="small"
                    type="link"
                    @click="openEditLibrary(item)"
                  >
                    编辑
                  </Button>
                  <Button
                    v-if="canDelete"
                    danger
                    size="small"
                    type="link"
                    @click="removeLibrary(item)"
                  >
                    删除
                  </Button>
                </div>
              </div>
            </article>
          </div>
          <Empty
            v-else-if="!libraryLoading"
            description="当前分类下暂无识别库，可点击右上角新增"
          />
        </Spin>
        <div
          v-if="libraryTotal > libraryQuery.pageSize"
          class="card-pagination"
        >
          <Pagination
            :current="libraryQuery.pageNo"
            :page-size="libraryQuery.pageSize"
            :total="libraryTotal"
            show-less-items
            @change="changeLibraryPage"
          />
        </div>
      </Card>

      <Card v-else class="library-detail">
        <template #title>
          <div class="detail-heading">
            <Button type="text" @click="leaveLibrary">
              <IconifyIcon icon="lucide:arrow-left" />返回识别库
            </Button>
            <span class="detail-heading__divider"></span>
            <div>
              <strong>{{ selectedLibrary.name }}</strong>
              <code>{{ selectedLibrary.code }}</code>
            </div>
          </div>
        </template>
        <template #extra>
          <div class="detail-actions">
            <Segmented
              :value="entryViewMode"
              :options="[
                { label: '卡片视图', value: 'CARD' },
                { label: '条目列表', value: 'LIST' },
              ]"
              @change="changeEntryView"
            />
            <Button v-if="canCreate" type="primary" @click="openCreateEntry">
              <IconifyIcon icon="lucide:user-round-plus" />录入条目
            </Button>
          </div>
        </template>

        <template v-if="entryViewMode === 'CARD'">
          <div class="filter-bar">
            <label class="filter-field filter-field--wide">
              <span>名称/编码</span>
              <Input
                v-model:value="entryQuery.name"
                allow-clear
                placeholder="请输入名称或编码"
                @press-enter="searchEntries"
              />
            </label>
            <label class="filter-field">
              <span>特征状态</span>
              <Select
                v-model:value="entryQuery.featureStatus"
                allow-clear
                :options="[
                  { label: '待提取', value: 'PENDING' },
                  { label: '已就绪', value: 'READY' },
                  { label: '提取失败', value: 'FAILED' },
                ]"
                placeholder="请选择"
              />
            </label>
            <div class="filter-actions">
              <Button @click="resetEntrySearch">重置</Button>
              <Button type="primary" @click="searchEntries">搜索</Button>
            </div>
          </div>
          <Spin :spinning="entryLoading">
            <div v-if="entryCards.length" class="entry-card-grid">
              <article
                v-for="item in entryCards"
                :key="item.id"
                class="entry-card"
              >
                <div class="entry-card__header">
                  <Avatar :size="64" :src="item.mediaRef" shape="square">
                    <IconifyIcon :icon="typeMeta.icon" />
                  </Avatar>
                  <div class="min-w-0">
                    <h3>{{ item.name }}</h3>
                    <span>{{ externalCodeTitle }}：{{
                        item.externalCode || '—'
                      }}</span>
                  </div>
                  <Badge
                    :status="item.status === 0 ? 'success' : 'default'"
                    :text="item.status === 0 ? '启用' : '停用'"
                  />
                </div>
                <p :title="attributeText(item)">{{ attributeText(item) }}</p>
                <p v-if="activeType === 'FACE'" class="text-sm text-gray-500">{{ extractionState(item).hint }}</p>
                <div class="entry-card__footer">
                  <Tag :color="activeType === 'FACE' ? extractionState(item).color : featureStatusColor(item.featureStatus)">
                    {{ activeType === 'FACE' ? extractionState(item).label : featureStatusText(item.featureStatus) }}
                  </Tag>
                  <div>
                    <Button v-if="activeType === 'FACE' && canExtract" size="small" type="link" :disabled="item.status !== 0 || !item.mediaRef || extractionState(item).processing" @click="openExtractEntry(item)">{{ extractionState(item).action }}</Button>
                    <Button
                      v-if="canUpdate"
                      size="small"
                      type="link"
                      @click="openEditEntry(item)"
                    >
                      编辑
                    </Button>
                    <Button
                      v-if="canDelete"
                      danger
                      size="small"
                      type="link"
                      @click="removeEntry(item)"
                    >
                      删除
                    </Button>
                  </div>
                </div>
              </article>
            </div>
            <Empty
              v-else-if="!entryLoading"
              description="当前识别库还没有条目，可点击右上角录入"
            />
          </Spin>
          <div v-if="entryTotal > entryQuery.pageSize" class="card-pagination">
            <Pagination
              :current="entryQuery.pageNo"
              :page-size="entryQuery.pageSize"
              :total="entryTotal"
              show-less-items
              @change="changeEntryPage"
            />
          </div>
        </template>

        <EntryGrid v-else>
          <template #media="{ row }">
            <Avatar :size="46" :src="row.mediaRef" shape="square">
              <IconifyIcon :icon="typeMeta.icon" />
            </Avatar>
          </template>
          <template #attributes="{ row }">
            <span :title="attributeText(row)">{{ attributeText(row) }}</span>
          </template>
          <template #featureStatus="{ row }">
            <Tag :color="activeType === 'FACE' ? extractionState(row).color : featureStatusColor(row.featureStatus)">
              {{ activeType === 'FACE' ? extractionState(row).label : featureStatusText(row.featureStatus) }}
            </Tag>
          </template>
          <template #status="{ row }">
            <Badge
              :status="row.status === 0 ? 'success' : 'default'"
              :text="row.status === 0 ? '启用' : '停用'"
            />
          </template>
          <template #actions="{ row }">
            <Button v-if="activeType === 'FACE' && canExtract" type="link" size="small" :disabled="row.status !== 0 || !row.mediaRef || extractionState(row).processing" @click="openExtractEntry(row)">{{ extractionState(row).action }}</Button>
            <TableAction
              :actions="[
                {
                  auth: ['ai-video:library:update'],
                  label: '编辑',
                  onClick: openEditEntry.bind(null, row),
                  type: 'link',
                },
                {
                  auth: ['ai-video:library:delete'],
                  danger: true,
                  label: '删除',
                  onClick: removeEntry.bind(null, row),
                  type: 'link',
                },
              ]"
            />
          </template>
        </EntryGrid>
      </Card>
    </div>
    <EntryAccess @references-changed="refreshEntries" />
  <FaceVerification />
  </Page>
</template>

<style scoped>
.recognition-page {
  padding-bottom: 4px;
}

.recognition-tabs {
  margin-bottom: -8px;
}

.engine-card {
  flex: none;
  overflow: hidden;
  color: hsl(var(--foreground));
  background: linear-gradient(
    135deg,
    hsl(var(--muted) / 42%) 0%,
    hsl(var(--card)) 62%
  );
  box-shadow: var(--ai-shadow-md);
}

.engine-card :deep(.ant-card-body) {
  display: grid;
  grid-template-areas: 'main action';
  grid-template-columns: minmax(0, 1fr) 312px;
  gap: 20px;
  padding: 20px;
}

.engine-main {
  display: flex;
  flex-direction: column;
  grid-area: main;
  gap: 18px;
  min-width: 0;
}

.engine-heading {
  display: flex;
  gap: 14px;
  align-items: center;
  min-width: 0;
}

.engine-heading__title {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.engine-heading h2 {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 22px;
  font-weight: 650;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.engine-heading p {
  margin: 0;
  color: hsl(var(--muted-foreground));
}

.engine-statistics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.engine-statistics :deep(.ant-statistic) {
  min-width: 0;
  padding: 12px 14px;
  background: hsl(var(--background) / 72%);
  border: 1px solid hsl(var(--primary) / 18%);
  border-radius: 10px;
}

.engine-statistics :deep(.ant-statistic-title) {
  color: hsl(var(--muted-foreground));
}

.engine-statistics :deep(.ant-statistic-content) {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 18px;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.engine-action {
  display: flex;
  flex-direction: column;
  grid-area: action;
  gap: 12px;
  justify-content: center;
  min-width: 0;
  padding: 16px;
  background: hsl(var(--background) / 82%);
  border: 1px solid hsl(var(--primary) / 18%);
  border-radius: 12px;
}

.engine-action__status {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
}

.engine-action__status > div {
  min-width: 0;
}

.engine-action__status strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.engine-action__status span {
  display: block;
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

.engine-action__icon-wrap {
  display: inline-flex !important;
  flex: 0 0 42px;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  margin: 0 !important;
  color: hsl(var(--primary)) !important;
  background: hsl(var(--primary) / 10%);
  border-radius: 10px;
}

.engine-action__icon {
  font-size: 23px;
}

.engine-action__note {
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

.engine-action__buttons {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.section-heading,
.detail-heading,
.detail-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.library-browser,
.library-detail {
  flex: none;
}

.library-detail :deep(.ant-card-head) {
  min-height: 68px;
  padding: 0 20px;
}

.library-detail :deep(.ant-card-head-wrapper) {
  min-height: 68px;
}

.library-detail :deep(.ant-card-head-title),
.library-detail :deep(.ant-card-extra) {
  padding: 10px 0;
}

.filter-bar {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(220px, 320px) auto;
  gap: 24px;
  align-items: center;
  padding: 16px 20px;
  margin-bottom: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 72%);
  border-radius: 10px;
}

.filter-field {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-width: 0;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.filter-field--wide {
  min-width: 260px;
}

.filter-field :deep(.ant-select) {
  width: 100%;
}

.filter-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.library-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.library-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  min-height: 230px;
  padding: 16px;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  box-shadow: var(--ai-shadow-sm);
  transition:
    border-color 150ms ease,
    box-shadow 150ms ease,
    transform 150ms ease;
}

.library-card:hover,
.library-card:focus-visible {
  outline: none;
  border-color: hsl(var(--primary) / 55%);
  box-shadow: 0 10px 28px rgb(37 99 235 / 12%);
  transform: translateY(-2px);
}

.library-card__header,
.library-card__footer,
.entry-card__header,
.entry-card__footer {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.library-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  font-size: 20px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 10px;
}

.library-card h3,
.entry-card h3 {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 16px;
  font-weight: 650;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.library-card code,
.detail-heading code {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.library-card > p,
.entry-card > p {
  display: -webkit-box;
  min-height: 40px;
  margin: 0;
  overflow: hidden;
  -webkit-line-clamp: 2;
  font-size: 12px;
  line-height: 1.65;
  color: hsl(var(--muted-foreground));
  -webkit-box-orient: vertical;
}

.library-card__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 12px 0;
  margin-top: auto;
  border-top: 1px solid hsl(var(--border) / 70%);
  border-bottom: 1px solid hsl(var(--border) / 70%);
}

.library-card__metrics > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.library-card__metrics > div + div {
  padding-left: 14px;
  border-left: 1px solid hsl(var(--border));
}

.library-card__metrics strong {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 16px;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.library-card__metrics span,
.library-card__footer > span {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.card-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.detail-heading__divider {
  width: 1px;
  height: 28px;
  background: hsl(var(--border));
}

.detail-heading strong {
  font-size: 15px;
  color: hsl(var(--foreground));
}

.entry-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.entry-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  min-height: 170px;
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.entry-card__header {
  align-items: flex-start;
}

.entry-card__header > div {
  flex: 1;
}

.entry-card__header span {
  display: block;
  margin-top: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.entry-card__footer {
  padding-top: 12px;
  margin-top: auto;
  border-top: 1px solid hsl(var(--border) / 70%);
}

@media (max-width: 1440px) {
  .library-card-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .engine-card :deep(.ant-card-body) {
    grid-template-areas: 'main' 'action';
    grid-template-columns: 1fr;
  }

  .engine-statistics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .engine-action {
    flex-direction: row;
    align-items: center;
    justify-content: flex-start;
  }

  .engine-action__status {
    flex: 1;
  }

  .engine-action__note {
    display: none;
  }

  .library-card-grid,
  .entry-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .engine-card :deep(.ant-card-body) {
    padding: 16px;
  }

  .engine-heading {
    align-items: flex-start;
  }

  .engine-heading__title {
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
  }

  .engine-heading h2 {
    white-space: normal;
  }

  .engine-statistics {
    grid-template-columns: 1fr 1fr;
  }

  .engine-action {
    flex-direction: column;
    align-items: stretch;
  }

  .engine-action__buttons,
  .filter-bar {
    grid-template-columns: 1fr;
  }

  .filter-bar {
    gap: 12px;
    align-items: stretch;
    padding: 14px;
  }

  .filter-field,
  .filter-field--wide {
    min-width: 0;
  }

  .library-card-grid,
  .entry-card-grid {
    grid-template-columns: 1fr;
  }

  .detail-heading__divider,
  .detail-heading code {
    display: none;
  }

  .detail-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
