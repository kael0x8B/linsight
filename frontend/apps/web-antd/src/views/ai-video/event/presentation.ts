import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoEventApi } from '#/api/ai-video/event';

export const eventTypes: Record<string, string> = {
  SAFETY_HELMET: '未佩戴安全帽',
  AREA_INTRUSION: '区域入侵',
  REFLECTIVE_VEST: '未穿反光衣',
  SMOKING: '吸烟',
  PHONE_CALL: '打电话',
  FIRE: '烟火告警',
  FALL: '人员跌倒',
  ENTRY_PERMISSION_DENIED: '入口权限异常',
  ENTRY_IDENTITY_UNCONFIRMED: '入口身份待核查',
  SLEEPING: '睡岗',
  ABSENCE: '离岗',
  PERSON_ABSENCE: '人员离岗',
  CROWD: '人员聚集',
  ANIMAL_INTRUSION: '动物闯入',
  BAG_STATIONARY: '箱包滞留',
  FACE_IDENTIFICATION: '人员库刷脸识别',
  FIGHTING: '疑似打架',
  FIRE_LANE_OCCUPIED: '消防通道占用',
  NONMOTOR_INTRUSION: '非机动车闯入',
  PEOPLE_COUNT: '人员统计',
  PEOPLE_LIMIT: '区域人数超限',
  PERSON_DWELL: '异常停留',
  PHONE_PRESENT: '禁带区域手机出现',
  VEHICLE_INTRUSION: '禁行车辆闯入',
  VEHICLE_STATIONARY: '车辆违停',
  VEHICLE_PLATE_RECOGNIZED: '车头车牌识别成功',
};
export const severityText: Record<string, string> = {
  CRITICAL: '严重',
  INFO: '提示',
  MAJOR: '重要',
  MINOR: '一般',
  URGENT: '紧急',
};
export const statusText: Record<string, string> = {
  ALARM: '待处理',
  ASSIGNED: '已指派',
  CLOSED: '已关闭',
  FALSE_POSITIVE: '误报',
  HANDLING: '处理中',
  RESOLVED: '已处理',
};
export const evidenceText: Record<string, string> = {
  READY: '证据齐全',
  PARTIAL: '部分证据已到达',
  PENDING: '等待证据',
  FAILED: '证据上传异常',
};
export const actionText: Record<string, string> = {
  CREATED: '确认告警',
  RECOVERED: '现场状态恢复',
  CLOSED: '事件关闭',
  ASSIGNED: '指派处置人',
  HANDLED: '完成处置',
  FALSE_POSITIVE: '标记误报',
  EVIDENCE_UPDATED: '更新证据',
};
export const severityColor: Record<string, string> = {
  CRITICAL: 'red',
  URGENT: 'red',
  INFO: 'blue',
  MAJOR: 'orange',
  MINOR: 'gold',
};
export const statusColor: Record<string, string> = {
  ALARM: 'red',
  ASSIGNED: 'blue',
  CLOSED: 'default',
  FALSE_POSITIVE: 'purple',
  HANDLING: 'cyan',
  RESOLVED: 'green',
};

export function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
export function recognitionResult(snapshot: unknown): string {
  const object = record(snapshot);
  const attributes = record(object.attributes);
  if (object.class === 'license_plate') {
    const plate = attributes.plateNumber;
    return typeof plate === 'string' && plate.trim()
      ? plate.trim()
      : '车牌未确认';
  }
  if (typeof attributes.displayLabel === 'string' && attributes.displayLabel.trim())
    return attributes.displayLabel.trim();
  if (typeof attributes.observedCount === 'number')
    return `区域人数：${attributes.observedCount}`;
  return '—';
}
export function formatTime(value: unknown) {
  if (value === undefined || value === null || value === '') return '未记录';
  let millis: number;
  if (typeof value === 'number') millis = value;
  else if (/^\d+$/.test(String(value))) millis = Number(value);
  else millis = Date.parse(String(value));
  if (!Number.isFinite(millis)) return '未记录';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
    .format(millis)
    .replaceAll('/', '-');
}
export function percent(value: unknown) {
  return typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 1
    ? `${(value * 100).toFixed(0)}%`
    : '未记录';
}
export function eventObject(
  event: AiVideoEventApi.Event,
): AiVideoCameraApi.OverlayObject | undefined {
  const source = record(event.objectSnapshot);
  const box = record(source.bbox);
  const values = [box.x, box.y, box.width, box.height];
  if (
    !values.every(
      (value) => typeof value === 'number' && Number.isFinite(value),
    )
  )
    return undefined;
  const [x, y, width, height] = values as number[];
  if (
    x === undefined ||
    y === undefined ||
    width === undefined ||
    height === undefined ||
    x < 0 ||
    y < 0 ||
    width <= 0 ||
    height <= 0 ||
    x + width > 1.000001 ||
    y + height > 1.000001
  )
    return undefined;
  const attributes = Object.fromEntries(
    Object.entries(record(source.attributes)).filter(
      ([, value]) =>
        value === null ||
        ['boolean', 'number', 'string'].includes(typeof value),
    ),
  ) as AiVideoCameraApi.OverlayObject['attributes'];
  return {
    bbox: { x, y, width, height },
    attributes,
    class: event.eventType.startsWith('ENTRY_')
      ? `${eventTypes[event.eventType] ?? '入口核验目标'} · 相似度`
      : String(source.class ?? '目标'),
    confidence: Number(
      (event.eventType.startsWith('ENTRY_')
        ? source.similarity
        : source.confidence) ?? 0,
    ),
    trackId:
      typeof source.trackId === 'string' ? source.trackId : event.trackId,
  };
}
export function eventFrame(
  event: AiVideoEventApi.Event,
): AiVideoCameraApi.OverlayFrame {
  const object = eventObject(event);
  return {
    frameId: `event:${event.id}`,
    sessionId: '',
    cameraId: event.cameraId,
    timestamp: event.occurredTime,
    sourceWidth: 1,
    sourceHeight: 1,
    objects: object ? [object] : [],
  };
}
export function recognitionScoreLabel(event: AiVideoEventApi.Event) {
  if (
    record(record(event.objectSnapshot).attributes).displayConfidence === null
  )
    return '识别结果';
  if (record(event.objectSnapshot).class === 'scene') return '区域人数';
  return event.eventType.startsWith('ENTRY_') ? '人脸相似度' : '识别置信度';
}
export function recognitionConfidence(event: AiVideoEventApi.Event) {
  if (event.eventType.startsWith('ENTRY_'))
    return percent(record(event.objectSnapshot).similarity);
  const attributes = record(record(event.objectSnapshot).attributes);
  if (record(event.objectSnapshot).class === 'license_plate')
    return percent(attributes.plateConfidence);
  if (attributes.displayConfidence === null)
    return String(attributes.displayLabel ?? '未记录');
  if (
    record(event.objectSnapshot).class === 'scene' &&
    typeof attributes.observedCount === 'number'
  ) {
    return `${attributes.observedCount} 人 / 门槛 ${attributes.thresholdCount ?? attributes.minimumCount ?? '未记录'} 人`;
  }
  return percent(
    event.eventType === 'SAFETY_HELMET'
      ? attributes.ppeConfidence
      : (record(event.objectSnapshot).confidence ?? event.maxConfidence),
  );
}
export function ruleSummary(value: unknown, regions: unknown = []): string {
  const node = record(value);
  const children = Array.isArray(node.children) ? node.children : [];
  const region = Array.isArray(regions)
    ? regions
        .map((item) => record(item))
        .find((item) => item.id === node.regionId)
    : undefined;
  switch (node.type) {
    case 'AND': {
      return children
        .map((child) => ruleSummary(child, regions))
        .join('，并且');
    }
    case 'COUNT': {
      return `目标数量${node.comparison === 'BELOW' ? '少于' : '达到'} ${node.min ?? node.count ?? node.minCount ?? node.minimumCount ?? '设定'} 个`;
    }
    case 'COUNT_BELOW': {
      return `${region?.name || '岗位区域'}人数少于 ${node.min} 人`;
    }
    case 'DURATION': {
      return `持续 ${node.seconds} 秒`;
    }
    case 'N_OF_M': {
      return `最近 ${node.m} 次分析中至少 ${node.n} 次符合条件`;
    }
    case 'NOT': {
      return `不满足（${ruleSummary(children[0], regions)}）`;
    }
    case 'OR': {
      return children
        .map((child) => `（${ruleSummary(child, regions)}）`)
        .join('，或');
    }
    case 'ROI_ENTER': {
      return `目标进入${region?.name || '指定识别区域'}`;
    }
    default: {
      return '包含暂无法展示的规则条件，请联系管理员核对';
    }
  }
}
export function settingsSummary(event: AiVideoEventApi.Event) {
  if (event.eventType.startsWith('ENTRY_')) {
    const config = record(event.taskSnapshot);
    const result = record(event.objectSnapshot);
    return [
      { label: '入口', value: String(config.name ?? '未记录') },
      { label: '比对方式', value: '本人主动刷脸，1:N 参考库检索' },
      {
        label: '确认条件',
        value: `最近 ${config.temporalM} 帧中至少 ${config.temporalN} 帧一致`,
      },
      { label: '相似度阈值', value: percent(config.similarityThreshold) },
      { label: '登记人员', value: String(result.personName ?? '身份未确认') },
      { label: '人员编号', value: String(result.externalCode ?? '未匹配') },
      { label: '实际推理设备', value: String(result.device ?? '未记录') },
      { label: '活体状态', value: '尚未验证，需现场人工核实' },
      { label: '证据范围', value: '本次主动核验期间的截图及录像' },
    ];
  }
  const parameters = record(record(event.taskSnapshot).parameters);
  const rule = record(event.ruleSnapshot);
  const regions = Array.isArray(rule.regions)
    ? rule.regions.map((item) => record(item))
    : [];
  const weekly = record(rule.schedule).weekly;
  const days = ['一', '二', '三', '四', '五', '六', '日'];
  const schedule = Array.isArray(weekly)
    ? weekly
        .map((item) => record(item))
        .map((item) => {
          const selected = Array.isArray(item.days) ? item.days : [];
          return `${new Set(selected).size === 7 ? '每天' : selected.map((day) => `周${days[Number(day) - 1] ?? '?'}`).join('、')} ${item.start}—${item.end}`;
        })
        .join('；')
    : '未记录';
  return [
    { label: '告警条件', value: ruleSummary(rule.condition, regions) },
    {
      label: '识别区域',
      value:
        regions.map((region) => region.name || '未命名区域').join('、') ||
        '未记录',
    },
    { label: '生效时间', value: schedule },
    {
      label: '目标分析频率',
      value:
        typeof parameters.sampleFps === 'number'
          ? `${parameters.sampleFps} 次/秒`
          : '未记录',
    },
    ...(event.eventType === 'SAFETY_HELMET'
      ? [
          { label: '安全帽判断门槛', value: percent(parameters.ppeConfidence) },
          {
            label: '人员确认门槛',
            value: percent(parameters.personConfidence),
          },
          {
            label: '无法确认时',
            value:
              parameters.unknownPolicy === 'NO_ALARM'
                ? '不触发告警，等待后续分析'
                : '未记录可展示的处理方式',
          },
        ]
      : []),
    {
      label: '重复告警间隔',
      value:
        typeof rule.cooldownSeconds === 'number'
          ? `${rule.cooldownSeconds} 秒`
          : '未记录',
    },
    {
      label: '恢复确认时间',
      value:
        typeof rule.recoverySeconds === 'number'
          ? `${rule.recoverySeconds} 秒`
          : '未记录',
    },
  ];
}

/** First uploaded evidence belongs to the immutable trigger snapshot. Later uploads must not replace it. */
export function firstEvidence(
  event: AiVideoEventApi.Event,
  type: 'SNAPSHOT' | 'VIDEO',
) {
  return event.media
    ?.filter((item) => item.mediaType === type && item.status === 'READY')
    .toSorted((a, b) => a.id - b.id)[0];
}

export function originalSnapshotAvailable(event: AiVideoEventApi.Event) {
  const original = firstEvidence(event, 'SNAPSHOT');
  if (!original || original.originalContentAvailable === false) return false;
  const key = (source?: string) => {
    if (!source) return undefined;
    try {
      const url = new URL(source);
      return url.origin + url.pathname;
    } catch {
      return source;
    }
  };
  return !event.media?.some(
    (media) =>
      media.mediaType === 'SNAPSHOT' &&
      media.sha256 !== original.sha256 &&
      key(media.accessUrl) &&
      key(media.accessUrl) === key(original.accessUrl),
  );
}
