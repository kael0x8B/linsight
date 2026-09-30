<script lang="ts" setup>
import type { PreviewTransport } from './preview-transport';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
} from 'vue';

import { Alert, Badge, Button, Empty, message, Spin } from 'ant-design-vue';

import {
  createWebRtcPreviewSession,
  getPreviewSession,
  releasePreviewSession,
} from '#/api/ai-video/camera';
import { $t } from '#/locales';

import {
  canCancelPreviewReconnect,
  evaluatePreviewMediaHealth,
  isPreviewSessionExpired,
  reconnectDelaySeconds,
  shouldReconnectFailedSession,
} from './camera-preview-health';
import { SourceClock } from './source-clock';

export type CameraPreviewPlaybackState =
  | 'ERROR'
  | 'IDLE'
  | 'PLAYING'
  | 'RECONNECTING'
  | 'STARTING'
  | 'WAITING';

const props = withDefaults(
  defineProps<{
    camera?: Partial<Pick<AiVideoCameraApi.Camera, 'protocol'>> &
      Pick<
        AiVideoCameraApi.Camera,
        'code' | 'id' | 'name' | 'onlineStatus' | 'status'
      >;
    compact?: boolean;
    muted?: boolean;
    nodeId?: number;
    overlayEnabled?: boolean;
    transport?: PreviewTransport;
  }>(),
  {
    camera: undefined,
    compact: false,
    muted: true,
    nodeId: undefined,
    overlayEnabled: true,
    transport: undefined,
  },
);

const emit = defineEmits<{
  error: [diagnosticId: string];
  session: [session?: AiVideoCameraApi.PreviewSession];
  stateChange: [state: CameraPreviewPlaybackState];
}>();

const ICE_GATHER_TIMEOUT_MS = 8000;
const DISCONNECTED_GRACE_MS = 8000;
const STABLE_PLAYBACK_RESET_MS = 30_000;
const SESSION_POLL_FAILURE_LIMIT = 3;
const playerHost = ref<HTMLElement>();
const playerContainer = ref<HTMLElement>();
const session = ref<AiVideoCameraApi.PreviewSession>();
const sessionLoading = ref(false);
const sessionError = ref('');
const diagnosticId = ref('');
const startupSeconds = ref(0);
const playbackState = ref<CameraPreviewPlaybackState>('IDLE');
const reconnectSeconds = ref(0);
const reconnectReason = ref('');
const reconnectCount = ref(0);
const lastReconnectReason = ref('');
const currentMuted = ref(props.muted);
const rtcConnectionState = ref<RTCPeerConnectionState>('new');
const rtcIceConnectionState = ref<RTCIceConnectionState>('new');
const inboundPackets = ref(0);
const lostPackets = ref(0);
const decodedFrames = ref(0);
const receivedFrames = ref(0);
const droppedFrames = ref(0);
const keyFramesDecoded = ref(0);
const pliCount = ref(0);
const jitterMillis = ref(0);
const jitterBufferDelayMillis = ref(0);
const decoderImplementation = ref('');
const playbackFps = ref<number>();
const negotiatedCodec = ref('');
const remoteTrackState = ref('none');
const displayVideo = shallowRef<HTMLVideoElement>();
const sourceClock = shallowRef<SourceClock>();

let peer: RTCPeerConnection | undefined;
let videoElement: HTMLVideoElement | undefined;
let startupTimer: ReturnType<typeof setInterval> | undefined;
let pollTimer: ReturnType<typeof setInterval> | undefined;
let reconnectTimer: ReturnType<typeof setInterval> | undefined;
let statsTimer: ReturnType<typeof setInterval> | undefined;
let disconnectedTimer: ReturnType<typeof setTimeout> | undefined;
let stablePlaybackTimer: ReturnType<typeof setTimeout> | undefined;
let requestGeneration = 0;
let reconnectAttempts = 0;
let pollFailureCount = 0;
let connectedAt: number | undefined;
let firstPacketAt: number | undefined;
let lastPacketAt: number | undefined;
let lastFrameAt: number | undefined;
let lastObservedPackets = 0;
let lastObservedFrames = 0;
let lastStatsTime: number | undefined;
const platformTransport: PreviewTransport = {
  create: createWebRtcPreviewSession,
  get: getPreviewSession,
  release: releasePreviewSession,
};
// Keep the owner of a session even when a caller replaces the current transport.
let sessionTransport: PreviewTransport = platformTransport;

const startupStage = computed(() => {
  if (startupSeconds.value < 3) return $t('page.aiVideo.live.stageSession');
  if (startupSeconds.value < 8) return $t('page.aiVideo.live.stageWebRtc');
  return $t('page.aiVideo.live.stageIce');
});
const playerStatusText = computed(() => {
  const key: Record<CameraPreviewPlaybackState, string> = {
    ERROR: 'playbackError',
    IDLE: 'idle',
    PLAYING: 'playing',
    RECONNECTING: 'reconnecting',
    STARTING: 'starting',
    WAITING: 'waiting',
  };
  return $t(`page.aiVideo.live.${key[playbackState.value]}`);
});
const playerStatus = computed(() => {
  if (playbackState.value === 'PLAYING') return 'success';
  if (playbackState.value === 'ERROR') return 'error';
  if (playbackState.value === 'IDLE') return 'default';
  return 'processing';
});

function setPlaybackState(state: CameraPreviewPlaybackState) {
  playbackState.value = state;
  emit('stateChange', state);
}

function clearTimers() {
  if (startupTimer) clearInterval(startupTimer);
  if (pollTimer) clearInterval(pollTimer);
  if (reconnectTimer) clearInterval(reconnectTimer);
  if (statsTimer) clearInterval(statsTimer);
  if (disconnectedTimer) clearTimeout(disconnectedTimer);
  if (stablePlaybackTimer) clearTimeout(stablePlaybackTimer);
  startupTimer = undefined;
  pollTimer = undefined;
  reconnectTimer = undefined;
  statsTimer = undefined;
  disconnectedTimer = undefined;
  stablePlaybackTimer = undefined;
}

function resetMediaHealth() {
  connectedAt = undefined;
  firstPacketAt = undefined;
  lastPacketAt = undefined;
  lastFrameAt = undefined;
  lastObservedPackets = 0;
  lastObservedFrames = 0;
  lastStatsTime = undefined;
  playbackFps.value = undefined;
  pollFailureCount = 0;
}

function disposePeer() {
  sourceClock.value?.close();
  sourceClock.value = undefined;
  displayVideo.value = undefined;
  peer?.close();
  peer = undefined;
  rtcConnectionState.value = 'closed';
  rtcIceConnectionState.value = 'closed';
  inboundPackets.value = 0;
  lostPackets.value = 0;
  decodedFrames.value = 0;
  receivedFrames.value = 0;
  droppedFrames.value = 0;
  keyFramesDecoded.value = 0;
  pliCount.value = 0;
  jitterMillis.value = 0;
  jitterBufferDelayMillis.value = 0;
  decoderImplementation.value = '';
  negotiatedCodec.value = '';
  remoteTrackState.value = 'none';
  resetMediaHealth();
  if (videoElement) {
    videoElement.pause();
    videoElement.srcObject = null;
  }
  videoElement = undefined;
  playerHost.value?.replaceChildren();
}

async function releaseCurrentSession() {
  const sessionId = session.value?.sessionId;
  session.value = undefined;
  emit('session', undefined);
  if (!sessionId) return;
  try {
    await sessionTransport.release(sessionId);
  } catch {
    // Runtime may have already reclaimed an idle session; release remains idempotent.
  }
}

async function stop() {
  clearTimers();
  disposePeer();
  setPlaybackState('IDLE');
  await releaseCurrentSession();
}

function extractDiagnosticId(error: unknown) {
  const text = error instanceof Error ? error.message : String(error);
  return text.match(/[0-9a-f]{8}-[0-9a-f-]{27}/i)?.[0] ?? '';
}

function createVideoElement() {
  const host = playerHost.value;
  if (!host) throw new Error('Preview host is unavailable');
  const element = document.createElement('video');
  element.autoplay = true;
  element.muted = currentMuted.value;
  element.playsInline = true;
  element.className = 'camera-preview-player__video';
  element.addEventListener('playing', () => {
    cancelReconnect();
    if (reconnectTimer) return;
    if (stablePlaybackTimer) clearTimeout(stablePlaybackTimer);
    stablePlaybackTimer = setTimeout(() => {
      reconnectAttempts = 0;
      stablePlaybackTimer = undefined;
    }, STABLE_PLAYBACK_RESET_MS);
    setPlaybackState('PLAYING');
  });
  element.addEventListener('waiting', () => {
    if (playbackState.value !== 'RECONNECTING') setPlaybackState('WAITING');
  });
  host.replaceChildren(element);
  videoElement = element;
  displayVideo.value = element;
  return element;
}

function cancelReconnect() {
  if (!canCancelPreviewReconnect(reconnectReason.value)) return;
  if (reconnectTimer) clearInterval(reconnectTimer);
  reconnectTimer = undefined;
  reconnectSeconds.value = 0;
  reconnectReason.value = '';
}

function scheduleReconnect(reason: string) {
  if (reconnectTimer || !props.camera?.id) return;
  reconnectCount.value += 1;
  lastReconnectReason.value = reason;
  setPlaybackState('RECONNECTING');
  reconnectReason.value = reason;
  reconnectSeconds.value = reconnectDelaySeconds(reconnectAttempts);
  reconnectAttempts += 1;
  reconnectTimer = setInterval(() => {
    reconnectSeconds.value -= 1;
    if (reconnectSeconds.value > 0) return;
    if (reconnectTimer) clearInterval(reconnectTimer);
    reconnectTimer = undefined;
    void start(false);
  }, 1000);
}

function bindPeer(currentPeer: RTCPeerConnection, generation: number) {
  const attachRemoteTrack = (
    track: MediaStreamTrack,
    streams: readonly MediaStream[] = [],
  ) => {
    if (generation !== requestGeneration || !videoElement) return;
    remoteTrackState.value = track.readyState;
    track.addEventListener('ended', () => {
      if (generation === requestGeneration)
        remoteTrackState.value = track.readyState;
    });
    videoElement.srcObject = streams[0] ?? new MediaStream([track]);
    // A newly attached MediaStream may not have delivered its first frame yet.
    // Chrome can reject this early play() call even though ICE and RTP are healthy,
    // so let the autoplay attribute retry instead of tearing down the session.
    void videoElement.play().catch(() => undefined);
  };
  currentPeer.addEventListener('track', (event) => {
    attachRemoteTrack(event.track, event.streams);
  });
  currentPeer.addEventListener('connectionstatechange', () => {
    if (generation !== requestGeneration || currentPeer !== peer) return;
    rtcConnectionState.value = currentPeer.connectionState;
    if (currentPeer.connectionState === 'failed') {
      if (disconnectedTimer) clearTimeout(disconnectedTimer);
      disconnectedTimer = undefined;
      scheduleReconnect('PEER_CONNECTION_FAILED');
    } else if (currentPeer.connectionState === 'connected') {
      connectedAt ??= performance.now();
      if (disconnectedTimer) clearTimeout(disconnectedTimer);
      disconnectedTimer = undefined;
      if (reconnectReason.value === 'PEER_CONNECTION_DISCONNECTED') {
        cancelReconnect();
      }
    } else if (currentPeer.connectionState === 'disconnected') {
      setPlaybackState('WAITING');
      if (!disconnectedTimer) {
        disconnectedTimer = setTimeout(() => {
          disconnectedTimer = undefined;
          if (
            generation === requestGeneration &&
            currentPeer === peer &&
            currentPeer.connectionState === 'disconnected'
          ) {
            scheduleReconnect('PEER_CONNECTION_DISCONNECTED');
          }
        }, DISCONNECTED_GRACE_MS);
      }
    }
  });
  currentPeer.addEventListener('iceconnectionstatechange', () => {
    if (generation === requestGeneration && currentPeer === peer) {
      rtcIceConnectionState.value = currentPeer.iceConnectionState;
    }
  });
  statsTimer = setInterval(async () => {
    if (generation !== requestGeneration || currentPeer !== peer) return;
    let stats: RTCStatsReport;
    try {
      stats = await currentPeer.getStats();
    } catch {
      return;
    }
    let videoReportFound = false;
    for (const report of stats.values()) {
      if (report.type === 'inbound-rtp' && report.kind === 'video') {
        videoReportFound = true;
        const now = performance.now();
        const packets = report.packetsReceived ?? 0;
        const frames = report.framesDecoded ?? 0;
        if (lastStatsTime !== undefined && now > lastStatsTime) {
          playbackFps.value = Math.max(
            0,
            ((frames - lastObservedFrames) * 1000) / (now - lastStatsTime),
          );
        }
        lastStatsTime = now;
        if (packets > lastObservedPackets) {
          firstPacketAt ??= now;
          lastPacketAt = now;
          lastObservedPackets = packets;
        }
        if (frames > lastObservedFrames) {
          lastFrameAt = now;
          lastObservedFrames = frames;
          if (currentPeer.connectionState === 'connected') cancelReconnect();
        }
        inboundPackets.value = packets;
        lostPackets.value = report.packetsLost ?? 0;
        decodedFrames.value = frames;
        receivedFrames.value = report.framesReceived ?? 0;
        droppedFrames.value = report.framesDropped ?? 0;
        keyFramesDecoded.value = report.keyFramesDecoded ?? 0;
        pliCount.value = report.pliCount ?? 0;
        jitterMillis.value = (report.jitter ?? 0) * 1000;
        jitterBufferDelayMillis.value = (report.jitterBufferDelay ?? 0) * 1000;
        decoderImplementation.value = report.decoderImplementation ?? '';
        const codec = report.codecId ? stats.get(report.codecId) : undefined;
        negotiatedCodec.value = codec?.mimeType ?? '';
        if (
          currentPeer.connectionState === 'connected' &&
          connectedAt !== undefined
        ) {
          const health = evaluatePreviewMediaHealth({
            connectedAt,
            decodedFrames: frames,
            documentHidden: document.hidden,
            firstPacketAt,
            lastFrameAt,
            lastPacketAt,
            now,
            packetsReceived: packets,
          });
          if (health.startsWith('RECONNECT_')) scheduleReconnect(health);
        }
      }
    }
    if (
      !videoReportFound &&
      currentPeer.connectionState === 'connected' &&
      connectedAt !== undefined
    ) {
      const health = evaluatePreviewMediaHealth({
        connectedAt,
        decodedFrames: 0,
        documentHidden: document.hidden,
        now: performance.now(),
        packetsReceived: 0,
      });
      if (health.startsWith('RECONNECT_')) scheduleReconnect(health);
    }
  }, 1000);
  return attachRemoteTrack;
}

function waitForIceGathering(currentPeer: RTCPeerConnection) {
  if (currentPeer.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      currentPeer.removeEventListener('icegatheringstatechange', handleChange);
      reject(new Error('WebRTC ICE gathering timed out'));
    }, ICE_GATHER_TIMEOUT_MS);
    function handleChange() {
      if (currentPeer.iceGatheringState !== 'complete') return;
      window.clearTimeout(timeout);
      currentPeer.removeEventListener('icegatheringstatechange', handleChange);
      resolve();
    }
    currentPeer.addEventListener('icegatheringstatechange', handleChange);
  });
}

function startSessionPolling(sessionId: string, generation: number) {
  pollTimer = setInterval(async () => {
    try {
      const current = await sessionTransport.get(sessionId);
      if (
        generation !== requestGeneration ||
        session.value?.sessionId !== sessionId
      )
        return;
      session.value = current;
      emit('session', current);
      pollFailureCount = 0;
      if (current.state === 'CLOSED') scheduleReconnect('SESSION_CLOSED');
      else if (
        current.state === 'FAILED' &&
        shouldReconnectFailedSession(
          peer?.connectionState,
          lastFrameAt,
          performance.now(),
        )
      )
        scheduleReconnect('SESSION_FAILED');
    } catch (error) {
      if (generation !== requestGeneration) return;
      diagnosticId.value = extractDiagnosticId(error) || diagnosticId.value;
      pollFailureCount += 1;
      if (isPreviewSessionExpired(error)) {
        scheduleReconnect('SESSION_EXPIRED');
      } else if (
        pollFailureCount >= SESSION_POLL_FAILURE_LIMIT &&
        peer?.connectionState !== 'connected'
      ) {
        scheduleReconnect('SESSION_POLL_FAILED');
      }
    }
  }, 3000);
}

async function start(resetBackoff = true) {
  if (resetBackoff) reconnectAttempts = 0;
  const generation = ++requestGeneration;
  await stop();
  if (generation !== requestGeneration) return;
  // Background tabs should not keep an encoded stream and decoder alive.
  // Recognition continues on the gateway independently of preview sessions.
  if (document.hidden) return;
  sessionError.value = '';
  diagnosticId.value = '';
  reconnectReason.value = '';
  startupSeconds.value = 0;
  if (
    !props.camera?.id ||
    (!props.nodeId && !props.transport) ||
    props.camera.onlineStatus === 2 ||
    props.camera.status !== 0
  )
    return;

  sessionLoading.value = true;
  setPlaybackState('STARTING');
  startupTimer = setInterval(() => (startupSeconds.value += 1), 1000);
  try {
    await nextTick();
    createVideoElement();
    const currentPeer = new RTCPeerConnection({
      bundlePolicy: 'max-bundle',
      iceServers: [],
      encodedInsertableStreams: true,
    } as RTCConfiguration);
    peer = currentPeer;
    const attachRemoteTrack = bindPeer(currentPeer, generation);
    const transceiver = currentPeer.addTransceiver('video', {
      direction: 'recvonly',
    });
    sourceClock.value = new SourceClock();
    sourceClock.value.connect(transceiver.receiver);
    const offer = await currentPeer.createOffer();
    await currentPeer.setLocalDescription(offer);
    await waitForIceGathering(currentPeer);
    if (!currentPeer.localDescription)
      throw new Error('WebRTC offer is unavailable');

    const transport = props.transport ?? platformTransport;
    const created = await transport.create({
      cameraId: props.camera.id,
      nodeId: props.nodeId ?? 0,
      offerSdp: currentPeer.localDescription.sdp,
      offerType: 'offer',
    });
    if (generation !== requestGeneration) {
      await transport.release(created.sessionId);
      currentPeer.close();
      return;
    }
    if (!created.answerSdp || created.answerType !== 'answer') {
      throw new Error('Runtime WebRTC answer is invalid');
    }
    sessionTransport = transport;
    session.value = created;
    emit('session', created);
    diagnosticId.value = created.diagnosticId;
    await currentPeer.setRemoteDescription({
      sdp: created.answerSdp,
      type: 'answer',
    });
    const receiverTrack = currentPeer
      .getReceivers()
      .map((receiver) => receiver.track)
      .find((track) => track.kind === 'video');
    if (receiverTrack && !videoElement?.srcObject)
      attachRemoteTrack(receiverTrack);
    if (playbackState.value !== 'PLAYING') setPlaybackState('WAITING');
    startSessionPolling(created.sessionId, generation);
  } catch (error) {
    if (generation !== requestGeneration) return;
    await releaseCurrentSession();
    disposePeer();
    sessionError.value = $t('page.aiVideo.live.sessionFailed');
    diagnosticId.value = extractDiagnosticId(error);
    setPlaybackState('ERROR');
    emit('error', diagnosticId.value);
    // A source upgrade can interrupt renegotiation while Runtime is starting.
    // Retry with the existing bounded backoff, keeping manual retry available.
    if (reconnectAttempts < 5) scheduleReconnect('SESSION_NEGOTIATION_FAILED');
  } finally {
    if (generation === requestGeneration) sessionLoading.value = false;
    if (startupTimer) clearInterval(startupTimer);
    startupTimer = undefined;
  }
}

function toggleMute() {
  currentMuted.value = !currentMuted.value;
  if (videoElement) videoElement.muted = currentMuted.value;
  return currentMuted.value;
}

async function toggleFullscreen() {
  if (!playerContainer.value) return;
  await (document.fullscreenElement
    ? document.exitFullscreen()
    : playerContainer.value.requestFullscreen());
}

function captureFrame() {
  if (!videoElement || !videoElement.videoWidth || videoElement.readyState < 2)
    return;
  const canvas = document.createElement('canvas');
  canvas.width = videoElement.videoWidth;
  canvas.height = videoElement.videoHeight;
  const context = canvas.getContext('2d');
  if (!context) return;
  context.drawImage(videoElement, 0, 0);
  return {
    dataUrl: canvas.toDataURL('image/jpeg', 0.9),
    width: canvas.width,
    height: canvas.height,
  };
}

function takeScreenshot() {
  const element = videoElement;
  const container = playerContainer.value;
  if (!element || !container || element.videoWidth === 0) {
    message.warning($t('page.aiVideo.live.screenshotUnavailable'));
    return;
  }
  const recognition = container.querySelector('.synchronized-video');
  if (recognition) {
    recognition.dispatchEvent(new Event('capture-recognition'));
    return;
  }
  const rect = container.getBoundingClientRect();
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(rect.width));
  canvas.height = Math.max(1, Math.round(rect.height));
  const context = canvas.getContext('2d');
  if (!context) return;
  context.fillStyle = '#050b14';
  context.fillRect(0, 0, canvas.width, canvas.height);
  const scale = Math.min(
    canvas.width / element.videoWidth,
    canvas.height / element.videoHeight,
  );
  const width = element.videoWidth * scale;
  const height = element.videoHeight * scale;
  const x = (canvas.width - width) / 2;
  const y = (canvas.height - height) / 2;
  context.drawImage(element, x, y, width, height);
  if (props.overlayEnabled) {
    const overlay =
      container.querySelector<HTMLCanvasElement>('.preview-overlay');
    if (overlay) context.drawImage(overlay, 0, 0, canvas.width, canvas.height);
  }
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${props.camera?.code ?? 'camera'}-${Date.now()}.png`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, 'image/png');
}

function handleVisibilityChange() {
  if (document.hidden) {
    requestGeneration += 1;
    void stop();
    return;
  }
  if (!peer) {
    void start(false);
    return;
  }
  const now = performance.now();
  connectedAt = now;
  if (inboundPackets.value > 0) {
    firstPacketAt ??= now;
    lastPacketAt = now;
  }
  if (decodedFrames.value > 0) lastFrameAt = now;
  void videoElement?.play().catch(() => undefined);
}

watch(
  [() => props.camera?.id, () => props.nodeId, () => props.transport],
  () => void start(true),
  { immediate: true },
);
watch(
  () => props.muted,
  (value) => {
    currentMuted.value = value;
    if (videoElement) videoElement.muted = value;
  },
);

onMounted(() =>
  document.addEventListener('visibilitychange', handleVisibilityChange),
);
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange);
  requestGeneration += 1;
  void stop();
});

defineExpose({
  captureFrame,
  start,
  stop,
  takeScreenshot,
  toggleFullscreen,
  toggleMute,
});
</script>

<template>
  <div
    ref="playerContainer"
    class="camera-preview-player"
    :class="{ compact }"
    :data-inbound-packets="inboundPackets"
    :data-lost-packets="lostPackets"
    :data-decoded-frames="decodedFrames"
    :data-received-frames="receivedFrames"
    :data-dropped-frames="droppedFrames"
    :data-key-frames-decoded="keyFramesDecoded"
    :data-pli-count="pliCount"
    :data-jitter-ms="jitterMillis"
    :data-jitter-buffer-delay-ms="jitterBufferDelayMillis"
    :data-decoder-implementation="decoderImplementation"
    :data-playback-fps="playbackFps"
    :data-negotiated-codec="negotiatedCodec"
    :data-reconnect-reason="reconnectReason"
    :data-reconnect-count="reconnectCount"
    :data-last-reconnect-reason="lastReconnectReason"
    :data-remote-track="remoteTrackState"
    :data-rtc-connection="rtcConnectionState"
    :data-rtc-ice-connection="rtcIceConnectionState"
  >
    <div ref="playerHost" class="camera-preview-player__host"></div>
    <slot
      name="overlay"
      :session="session"
      :video="displayVideo"
      :clock="sourceClock"
    ></slot>

    <div v-if="!camera" class="camera-preview-player__state">
      <Empty :description="$t('page.aiVideo.live.selectCamera')" />
    </div>
    <div v-else-if="camera.status !== 0" class="camera-preview-player__state">
      <Alert
        :message="$t('page.aiVideo.live.cameraDisabled')"
        show-icon
        type="warning"
      />
    </div>
    <div v-else-if="!nodeId && !transport" class="camera-preview-player__state">
      <Alert
        :message="$t('page.aiVideo.live.selectReadyNode')"
        show-icon
        type="warning"
      />
    </div>
    <div
      v-else-if="camera.onlineStatus === 2"
      class="camera-preview-player__state"
    >
      <Alert
        :message="$t('page.aiVideo.live.cameraOffline')"
        show-icon
        type="error"
      />
    </div>
    <div
      v-else-if="sessionLoading"
      class="camera-preview-player__state camera-preview-player__state--dark"
    >
      <Spin />
      <strong>{{ startupStage }}</strong>
      <span v-if="startupSeconds >= 8">{{
        $t('page.aiVideo.live.slowStartup', [startupSeconds])
      }}</span>
    </div>
    <div
      v-else-if="sessionError"
      class="camera-preview-player__state camera-preview-player__state--dark"
    >
      <Alert :message="sessionError" show-icon type="error">
        <template #description>
          <span v-if="diagnosticId" class="camera-preview-player__diagnostic">
            {{ $t('page.aiVideo.live.diagnosticId') }}: {{ diagnosticId }}
          </span>
        </template>
        <template #action>
          <Button size="small" @click="() => start()">
            {{ $t('page.aiVideo.live.retry') }}
          </Button>
        </template>
      </Alert>
    </div>
    <div
      v-else-if="playbackState === 'RECONNECTING'"
      class="camera-preview-player__reconnect"
    >
      {{ $t('page.aiVideo.live.reconnectCountdown', [reconnectSeconds]) }}
    </div>

    <div v-if="camera" class="camera-preview-player__statusbar">
      <span class="camera-preview-player__camera"
        >[{{ camera.protocol }}] {{ camera.name }}</span
      >
      <span><Badge :status="playerStatus" />{{ playerStatusText }}</span>
      <span v-if="session">WebRTC · SUB</span>
      <span v-if="playbackFps !== undefined">{{
        $t('page.aiVideo.recognition.videoRate', [playbackFps.toFixed(1)])
      }}</span>
      <span
        v-if="diagnosticId && !compact"
        class="camera-preview-player__diagnostic"
        >{{ diagnosticId }}</span
      >
    </div>
  </div>
</template>

<style scoped>
.camera-preview-player {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 240px;
  overflow: hidden;
  color: #cbd5e1;
  background: #030711;
}

.camera-preview-player__host {
  width: 100%;
  height: 100%;
}

.camera-preview-player :deep(.camera-preview-player__video) {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: transparent;
}

.camera-preview-player__state,
.camera-preview-player__reconnect {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #030711;
}

.camera-preview-player__state--dark {
  flex-direction: column;
  gap: 12px;
  color: #dbeafe;
}

.camera-preview-player__reconnect {
  align-items: flex-start;
  justify-content: flex-end;
  background: rgb(3 7 17 / 42%);
}

.camera-preview-player__statusbar {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 4;
  display: flex;
  gap: 14px;
  align-items: center;
  min-height: 36px;
  padding: 7px 10px;
  font-size: 12px;
  background: linear-gradient(transparent, rgb(0 0 0 / 88%));
}

.camera-preview-player__camera {
  margin-right: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  color: #f8fafc;
  white-space: nowrap;
}

.camera-preview-player__diagnostic {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.camera-preview-player.compact {
  min-height: 0;
}

.camera-preview-player.compact .camera-preview-player__statusbar {
  gap: 8px;
  min-height: 28px;
  padding: 4px 8px;
  font-size: 11px;
}

.camera-preview-player.compact .camera-preview-player__state {
  padding: 10px;
}
</style>
