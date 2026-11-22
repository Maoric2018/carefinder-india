import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Inter';
import timingJson from './timing.json';

export const {fontFamily} = loadFont('normal', {weights: ['400', '500', '600', '700', '800', '900'], subsets: ['latin']});

// ---------- palette ----------
export const C = {
  bg: '#051216',
  panel: 'rgba(255,255,255,0.055)',
  panelStrong: 'rgba(8,24,29,0.86)',
  line: 'rgba(255,255,255,0.12)',
  teal: '#14B8A6',
  tealDeep: '#0F766E',
  tealSoft: '#5EEAD4',
  text: '#F1F5F9',
  muted: '#94A3B8',
  amber: '#F59E0B',
  red: '#F05252',
  green: '#10B981',
  blue: '#60A5FA',
};

export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// ---------- timeline ----------
type Word = {w: string; s: number; e: number};
type Timing = Record<string, {duration: number; words: Word[]}>;
export const timing = timingJson as unknown as Timing;

export const FPS = 30;
export const PAD = 6; // frames of picture before the voice starts in each scene
export const OVERLAP = 6; // crossfade between scenes

export const ORDER = ['s1_hook', 's2_data', 's3_demo', 's4_results', 's5_pune', 's6_model', 's7_odds', 's8_checks', 's9_access',
  's10_plan', 's11_close'] as const;
export type SceneId = (typeof ORDER)[number];
const TAIL: Record<SceneId, number> = {
  s1_hook: 0.2, s2_data: 0.1, s3_demo: 0.1, s4_results: 0.1, s5_pune: 0.1, s6_model: 0.1, s7_odds: 0.1,
  s8_checks: 0.1, s9_access: 0.1, s10_plan: 0.2, s11_close: 1.0,
};

export const SCENES = (() => {
  let from = 0;
  return ORDER.map((id) => {
    const dur = PAD + Math.ceil(timing[id].duration * FPS) + Math.ceil(TAIL[id] * FPS);
    const sc = {id, from, dur};
    from += dur - OVERLAP;
    return sc;
  });
})();
export const TOTAL = SCENES[SCENES.length - 1].from + SCENES[SCENES.length - 1].dur;
export const sceneLen = (id: SceneId) => SCENES.find((s) => s.id === id)!.dur;

const norm = (w: string) => w.toLowerCase().replace(/[^a-z0-9-]/g, '');

/** Index of the first word of `phrase` (nth occurrence) in a scene's voiceover. */
const findPhrase = (id: SceneId, phrase: string, nth = 0) => {
  const words = timing[id].words;
  const target = phrase.split(' ').map(norm);
  let count = 0;
  for (let i = 0; i < words.length; i++) {
    if (target.every((t, j) => words[i + j] && norm(words[i + j].w) === t)) {
      if (count === nth) return i;
      count++;
    }
  }
  throw new Error(`cue not found: ${id} "${phrase}"`);
};

/** Scene-relative frame at which `phrase` starts (or ends) being spoken. */
export const cue = (id: SceneId, phrase: string, opts: {nth?: number; end?: boolean; offset?: number} = {}) => {
  const i = findPhrase(id, phrase, opts.nth ?? 0);
  const words = timing[id].words;
  const n = phrase.split(' ').length;
  const t = opts.end ? words[i + n - 1].e : words[i].s;
  return PAD + Math.round((t + (opts.offset ?? 0)) * FPS);
};

export const wordsOf = (id: SceneId, phrase: string) => {
  const i = findPhrase(id, phrase);
  return timing[id].words.slice(i, i + phrase.split(' ').length);
};

// ---------- motion helpers ----------
export const ease = (f: number, at: number, dur = 18) =>
  interpolate(f, [at, at + dur], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});

export const easeIO = (f: number, at: number, dur = 18) =>
  interpolate(f, [at, at + dur], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});

export const usePop = (at: number, damping = 14) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: f - at, fps, config: {damping, stiffness: 170, mass: 0.8}});
};

/** Fade/slide in at `at`, optionally out at `out`. */
export const Appear: React.FC<{
  at: number; out?: number; dy?: number; dx?: number; dur?: number; scale?: boolean;
  style?: React.CSSProperties; children: React.ReactNode;
}> = ({at, out, dy = 26, dx = 0, dur = 16, scale, style, children}) => {
  const f = useCurrentFrame();
  const p = ease(f, at, dur);
  const q = out === undefined ? 1 : 1 - easeIO(f, out, 12);
  const s = scale ? 0.92 + 0.08 * p : 1;
  return (
    <div style={{opacity: p * q, transform: `translate(${(1 - p) * dx}px, ${(1 - p) * dy}px) scale(${s})`, ...style}}>
      {children}
    </div>
  );
};

export const Counter: React.FC<{to: number; at: number; dur?: number; from?: number; suffix?: string; decimals?: number}> = ({
  to, at, dur = 30, from = 0, suffix = '', decimals = 0,
}) => {
  const f = useCurrentFrame();
  const v = interpolate(f, [at, at + dur], [from, to], {...clamp, easing: Easing.out(Easing.cubic)});
  const txt = decimals ? v.toFixed(decimals) : Math.round(v).toLocaleString('en-US');
  return <span style={{fontVariantNumeric: 'tabular-nums'}}>{txt}{suffix}</span>;
};

// ---------- icons (lucide-style strokes) ----------
const ICONS: Record<string, React.ReactNode> = {
  pin: (<><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="3" /></>),
  check: <path d="M20 6 9 17l-5-5" />,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  flag: (<><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><path d="M4 22v-7" /></>),
  globe: (<><circle cx="12" cy="12" r="10" /><path d="M2 12h20" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></>),
  doc: (<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M16 13H8" /><path d="M16 17H8" /></>),
  search: (<><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></>),
  alert: (<><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></>),
  hospital: (<><path d="M3 21h18" /><path d="M5 21V7l7-4 7 4v14" /><path d="M10 10h4M12 8v4" /></>),
  mail: (<><rect x="2" y="4" width="20" height="16" rx="2" /><path d="m22 6-10 7L2 6" /></>),
  layers: (<><path d="M12 2 2 7l10 5 10-5-10-5z" /><path d="m2 17 10 5 10-5" /><path d="m2 12 10 5 10-5" /></>),
  chat: <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />,
  quote: (<><path d="M7 7h4v4c0 3-1.5 5-4 6" /><path d="M15 7h4v4c0 3-1.5 5-4 6" /></>),
  ruler: (<><path d="M3 12h18" /><path d="M3 8v8M21 8v8" /><circle cx="12" cy="12" r="2" /></>),
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  heart: <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />,
  tag: (<><path d="M12 2H2v10l9.29 9.29a1 1 0 0 0 1.41 0l8.59-8.59a1 1 0 0 0 0-1.41Z" /><circle cx="7" cy="7" r="1.5" /></>),
  merge: (<><circle cx="6" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="12" r="3" /><path d="M9 6c4 0 6 2 6 6M9 18c4 0 6-2 6-6" /></>),
};

export const Icon: React.FC<{name: keyof typeof ICONS | string; size?: number; color?: string; sw?: number}> = ({
  name, size = 28, color = 'currentColor', sw = 2.2,
}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round">
    {ICONS[name]}
  </svg>
);

// ---------- brand ----------
export const Logo: React.FC<{size?: number}> = ({size = 96}) => (
  <div style={{
    width: size, height: size, borderRadius: size * 0.27, flexShrink: 0,
    background: 'linear-gradient(135deg, #2DD4BF 0%, #0F766E 100%)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    boxShadow: `0 ${size * 0.12}px ${size * 0.45}px rgba(20,184,166,0.45), inset 0 1px 0 rgba(255,255,255,0.35)`,
  }}>
    <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none">
      <path d="M12 22s7.5-7 7.5-12.5a7.5 7.5 0 0 0-15 0C4.5 15 12 22 12 22z" fill="white" />
      <path d="M12 6.2v6.4M8.8 9.4h6.4" stroke="#0F766E" strokeWidth={2.4} strokeLinecap="round" />
    </svg>
  </div>
);

// ---------- backgrounds ----------
export const Bg: React.FC<{grid?: boolean}> = ({grid = true}) => {
  const f = useCurrentFrame();
  const x = 22 + Math.sin(f / 80) * 6;
  const y = 24 + Math.cos(f / 95) * 6;
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <AbsoluteFill style={{
        background: `radial-gradient(1000px 760px at ${x}% ${y}%, rgba(20,184,166,0.20), transparent 62%),
                     radial-gradient(900px 760px at ${86 - x / 5}% ${84 - y / 5}%, rgba(56,130,246,0.12), transparent 60%)`,
      }} />
      {grid && (
        <AbsoluteFill style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          backgroundPosition: `${(f * 0.25) % 64}px ${(f * 0.15) % 64}px`,
          WebkitMaskImage: 'radial-gradient(ellipse at 50% 45%, black 25%, transparent 78%)',
          maskImage: 'radial-gradient(ellipse at 50% 45%, black 25%, transparent 78%)',
        }} />
      )}
    </AbsoluteFill>
  );
};

export const PhotoBg: React.FC<{src: string; opacity?: number; from?: number; to?: number; origin?: string; flip?: boolean; len: number}> = ({
  src, opacity = 1, from = 1.04, to = 1.12, origin = '50% 50%', flip, len,
}) => {
  const f = useCurrentFrame();
  const s = interpolate(f, [0, len], [from, to]);
  return (
    <AbsoluteFill style={{opacity, overflow: 'hidden'}}>
      <AbsoluteFill style={{transform: flip ? 'scaleX(-1)' : undefined}}>
        <Img src={staticFile(src)} style={{
          width: '100%', height: '100%', objectFit: 'cover',
          transform: `scale(${s})`, transformOrigin: origin,
        }} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------- chrome ----------
export const Chapter: React.FC<{n: string; label: string}> = ({n, label}) => {
  const f = useCurrentFrame();
  const p = ease(f, 8, 18);
  return (
    <div style={{position: 'absolute', left: 96, top: 60, display: 'flex', alignItems: 'center', gap: 16, opacity: p, transform: `translateX(${(1 - p) * -30}px)`}}>
      <div style={{fontSize: 20, fontWeight: 800, color: C.bg, background: C.tealSoft, borderRadius: 8, padding: '5px 11px', letterSpacing: 1}}>{n}</div>
      <div style={{fontSize: 21, fontWeight: 700, letterSpacing: 3.5, textTransform: 'uppercase', color: 'rgba(241,245,249,0.85)'}}>{label}</div>
    </div>
  );
};

export const Glass: React.FC<{style?: React.CSSProperties; children: React.ReactNode; accent?: string}> = ({style, children, accent}) => (
  <div style={{
    background: 'linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.035))',
    border: `1px solid ${accent ? accent + '66' : C.line}`,
    borderRadius: 22,
    boxShadow: `0 24px 70px rgba(0,0,0,0.35)${accent ? `, 0 0 40px ${accent}22` : ''}`,
    backdropFilter: 'blur(14px)',
    ...style,
  }}>
    {children}
  </div>
);

export const Pill: React.FC<{icon?: string; color?: string; children: React.ReactNode; size?: number; solid?: boolean}> = ({
  icon, color = C.tealSoft, children, size = 30, solid,
}) => (
  <div style={{
    display: 'inline-flex', alignItems: 'center', gap: size * 0.4,
    padding: `${size * 0.36}px ${size * 0.75}px`, borderRadius: 999,
    background: solid ? color : `${color}1f`, border: `2px solid ${color}88`,
    color: solid ? C.bg : color, fontSize: size, fontWeight: 700, whiteSpace: 'nowrap',
  }}>
    {icon && <Icon name={icon} size={size * 1.05} color={solid ? C.bg : color} sw={2.4} />}
    {children}
  </div>
);

export const Browser: React.FC<{w: number; h: number; url: string; dark?: boolean; children: React.ReactNode}> = ({w, h, url, dark, children}) => (
  <div style={{width: w, borderRadius: 18, overflow: 'hidden', background: dark ? '#0B0F14' : '#F6F7F9',
    boxShadow: '0 50px 140px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.10)'}}>
    <div style={{height: 46, background: dark ? '#161B22' : '#E7EBEF', display: 'flex', alignItems: 'center', padding: '0 20px', gap: 9}}>
      {['#FF5F57', '#FEBC2E', '#28C840'].map((c) => <div key={c} style={{width: 14, height: 14, borderRadius: 7, background: c}} />)}
      <div style={{marginLeft: 24, width: 620, height: 30, borderRadius: 8, background: dark ? '#0B0F14' : '#FFFFFF',
        display: 'flex', alignItems: 'center', gap: 10, padding: '0 14px', fontSize: 17, color: dark ? '#9AA4B2' : '#5B6675', fontWeight: 500}}>
        <Icon name="shield" size={16} color={dark ? '#9AA4B2' : '#5B6675'} />
        {url}
      </div>
    </div>
    <div style={{width: w, height: h, position: 'relative', overflow: 'hidden'}}>{children}</div>
  </div>
);

/** A screenshot drawn at scale s, with rounded corners. Children are positioned in image pixels * s. */
export const Shot: React.FC<{src: string; w: number; h: number; s: number; radius?: number; children?: React.ReactNode; shadow?: boolean}> = ({
  src, w, h, s, radius = 22, children, shadow = true,
}) => (
  <div style={{position: 'relative', width: w * s, height: h * s}}>
    <Img src={staticFile(src)} style={{width: w * s, height: h * s, borderRadius: radius, display: 'block',
      boxShadow: shadow ? '0 40px 110px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.06)' : undefined}} />
    {children}
  </div>
);

/** Animated highlight ring over a region [x1,y1,x2,y2] of a screenshot drawn at scale s. */
export const Box: React.FC<{
  r: [number, number, number, number]; s: number; at: number; until?: number; color?: string;
  label?: string; side?: 'top' | 'bottom' | 'right' | 'left' | 'topright'; pad?: number; radius?: number; fill?: boolean;
}> = ({r, s, at, until, color = C.teal, label, side = 'top', pad = 8, radius = 14, fill}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (f < at - 1 || (until !== undefined && f > until + 14)) return null;
  const pop = spring({frame: f - at, fps, config: {damping: 15, stiffness: 180}});
  const out = until === undefined ? 1 : 1 - easeIO(f, until, 12);
  const op = Math.min(ease(f, at, 6), out);
  const ring = ease(f, at, 22);
  const [x1, y1, x2, y2] = r;
  const box: React.CSSProperties = {position: 'absolute', left: x1 * s - pad, top: y1 * s - pad, width: (x2 - x1) * s + 2 * pad, height: (y2 - y1) * s + 2 * pad};
  const labelPos: React.CSSProperties =
    side === 'top' ? {left: 0, bottom: '100%', marginBottom: 12}
      : side === 'topright' ? {right: 0, bottom: '100%', marginBottom: 12}
        : side === 'bottom' ? {left: 0, top: '100%', marginTop: 12}
          : side === 'right' ? {left: '100%', top: '50%', marginLeft: 18, transform: 'translateY(-50%)'}
            : {right: '100%', top: '50%', marginRight: 18, transform: 'translateY(-50%)'};
  return (
    <div style={{...box, opacity: op, pointerEvents: 'none'}}>
      <div style={{position: 'absolute', inset: 0, borderRadius: radius, border: `4px solid ${color}`,
        background: fill ? `${color}14` : undefined,
        boxShadow: `0 0 0 5px ${color}30, 0 0 36px ${color}90`, transform: `scale(${1.08 - 0.08 * pop})`}} />
      <div style={{position: 'absolute', inset: 0, borderRadius: radius, border: `3px solid ${color}`,
        opacity: 1 - ring, transform: `scale(${1 + ring * 0.12})`}} />
      {label && (
        <div style={{position: 'absolute', ...labelPos, whiteSpace: 'nowrap', background: color, color: '#04161A',
          fontSize: 25, fontWeight: 800, padding: '7px 16px', borderRadius: 10,
          boxShadow: '0 10px 30px rgba(0,0,0,0.35)', transformOrigin: 'left center',
          opacity: ease(f, at + 4, 10)}}>
          {label}
        </div>
      )}
    </div>
  );
};

/** Pan/zoom over content of natural size cw x ch shown in a w x h window. keys: focus point + zoom at frames. */
export const Camera: React.FC<{w: number; h: number; cw: number; ch: number; keys: {f: number; x: number; y: number; z: number}[]; children: React.ReactNode}> = ({
  w, h, cw, ch, keys, children,
}) => {
  const f = useCurrentFrame();
  const ks = keys.length === 1 ? [keys[0], {...keys[0], f: keys[0].f + 1}] : keys;
  const fr = ks.map((k) => k.f);
  const opt = {...clamp, easing: Easing.inOut(Easing.cubic)};
  const x = interpolate(f, fr, ks.map((k) => k.x), opt);
  const y = interpolate(f, fr, ks.map((k) => k.y), opt);
  const z = interpolate(f, fr, ks.map((k) => k.z), opt);
  const S = (w / cw) * z;
  const tx = Math.min(0, Math.max(w - cw * S, w / 2 - x * S));
  const ty = Math.min(0, Math.max(h - ch * S, h / 2 - y * S));
  return (
    <div style={{width: w, height: h, overflow: 'hidden', position: 'relative'}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: cw, height: ch, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${S})`}}>
        {children}
      </div>
    </div>
  );
};

// ---------- text ----------
/** Words appear one by one exactly as they are spoken. */
export const SpokenLine: React.FC<{id: SceneId; phrase: string; size: number; accent?: string[]; color?: string; weight?: number}> = ({
  id, phrase, size, accent = [], color = C.text, weight = 800,
}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ws = wordsOf(id, phrase);
  return (
    <div style={{fontSize: size, fontWeight: weight, lineHeight: 1.08, letterSpacing: -size * 0.025, color}}>
      {ws.map((w, i) => {
        const at = PAD + Math.round(w.s * FPS) - 2;
        const p = spring({frame: f - at, fps, config: {damping: 18, stiffness: 160}});
        const isAccent = accent.includes(norm(w.w));
        return (
          <span key={i} style={{display: 'inline-block', marginRight: size * 0.26, opacity: Math.min(1, p * 1.4),
            transform: `translateY(${(1 - p) * size * 0.45}px)`,
            color: isAccent ? undefined : color,
            backgroundImage: isAccent ? 'linear-gradient(90deg, #5EEAD4, #14B8A6)' : undefined,
            WebkitBackgroundClip: isAccent ? 'text' : undefined,
            WebkitTextFillColor: isAccent ? 'transparent' : undefined}}>
            {w.w}
          </span>
        );
      })}
    </div>
  );
};

// ---------- captions ----------
const groupCache: Record<string, Word[][]> = {};
const groups = (id: SceneId) => {
  if (groupCache[id]) return groupCache[id];
  // sentences first, then split long sentences into balanced chunks (no orphan words)
  const sentences: Word[][] = [];
  let cur: Word[] = [];
  for (const w of timing[id].words) {
    cur.push(w);
    if (/[.?!]$/.test(w.w)) {
      sentences.push(cur);
      cur = [];
    }
  }
  if (cur.length) sentences.push(cur);
  const out: Word[][] = [];
  for (const s of sentences) {
    const total = s.reduce((a, w) => a + w.w.length + 1, 0);
    const n = Math.ceil(total / 50);
    if (n <= 1) {
      out.push(s);
      continue;
    }
    const target = total / n;
    let chunk: Word[] = [];
    let len = 0;
    let made = 0;
    s.forEach((w, i) => {
      chunk.push(w);
      len += w.w.length + 1;
      const remaining = s.length - i - 1;
      const punct = /[,:;]$/.test(w.w);
      if (made < n - 1 && remaining >= 3 && (len >= target || (punct && len >= target * 0.6))) {
        out.push(chunk);
        chunk = [];
        len = 0;
        made++;
      }
    });
    if (chunk.length) out.push(chunk);
  }
  groupCache[id] = out;
  return out;
};

export const Captions: React.FC<{id: SceneId; from?: number; until?: number}> = ({id, from = -1, until = 1e9}) => {
  const f = useCurrentFrame();
  const t = (f - PAD) / FPS;
  const gs = groups(id);
  let gi = -1;
  for (let i = 0; i < gs.length; i++) if (gs[i][0].s - 0.1 <= t) gi = i;
  if (gi < 0) return null;
  const g = gs[gi];
  if (g[0].s < from || g[0].s > until) return null;
  const end = g[g.length - 1].e;
  const startF = PAD + (g[0].s - 0.1) * FPS;
  const fadeIn = interpolate(f, [startF, startF + 4], [0, 1], clamp);
  const last = gi === gs.length - 1;
  const fadeOut = last ? interpolate(t, [end + 0.35, end + 0.6], [1, 0], clamp) : 1;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 44, display: 'flex', justifyContent: 'center', opacity: fadeIn * fadeOut}}>
      <div style={{maxWidth: 1560, padding: '13px 30px 15px', borderRadius: 16, background: 'rgba(2,10,13,0.74)',
        border: '1px solid rgba(255,255,255,0.08)', fontSize: 37, fontWeight: 600, color: C.text, lineHeight: 1.3, textAlign: 'center',
        letterSpacing: -0.3, boxShadow: '0 12px 40px rgba(0,0,0,0.35)'}}>
        {g.map((w) => w.w).join(' ')}
      </div>
    </div>
  );
};
