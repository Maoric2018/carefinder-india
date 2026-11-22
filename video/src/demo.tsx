import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {
  Appear, Bg, Box, Browser, C, Captions, Chapter, Counter, Glass, Icon, Logo, Pill,
  clamp, cue, ease, easeIO, sceneLen, usePop,
} from './lib';

// The real app, captured from the deployed Databricks App at 1512x805 (1x) with 2x crops layered on top
// at their exact page positions, so camera zooms stay sharp.
export const VW = 1512;
export const VH = 805;
type Key = {f: number; x: number; y: number; z: number};
type CKey = {f: number; x: number; y: number};

const sortKeys = <T extends {f: number}>(ks: T[]) => {
  const out = [...ks].sort((a, b) => a.f - b.f);
  for (let i = 1; i < out.length; i++) if (out[i].f <= out[i - 1].f) out[i] = {...out[i], f: out[i - 1].f + 1};
  return out.length === 1 ? [out[0], {...out[0], f: out[0].f + 1}] : out;
};

export const cam = (f: number, keys: Key[], pageH: number) => {
  const ks = sortKeys(keys);
  const fr = ks.map((k) => k.f);
  const opt = {...clamp, easing: Easing.inOut(Easing.cubic)};
  const x = interpolate(f, fr, ks.map((k) => k.x), opt);
  const y = interpolate(f, fr, ks.map((k) => k.y), opt);
  const S = interpolate(f, fr, ks.map((k) => k.z), opt);
  const tx = Math.min(0, Math.max(VW - VW * S, VW / 2 - x * S));
  const ty = Math.min(0, Math.max(VH - pageH * S, VH / 2 - y * S));
  return {S, tx, ty};
};

const CursorIcon: React.FC<{x: number; y: number; press: number; opacity: number}> = ({x, y, press, opacity}) => (
  <svg width={34} height={34} viewBox="0 0 24 24" style={{position: 'absolute', left: x - 4, top: y - 3, opacity,
    transform: `scale(${1 - 0.18 * press})`, transformOrigin: '4px 3px', filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.35))'}}>
    <path d="M4 2 L4 19.5 L8.6 15.2 L11.7 22 L14.8 20.6 L11.8 13.9 L18.2 13.9 Z" fill="#0B1220" stroke="white" strokeWidth={1.6} strokeLinejoin="round" />
  </svg>
);

/** Browser viewport over a page. Children are laid out in page pixels. Cursor positions are page pixels too. */
export const Viewport: React.FC<{
  keys: Key[]; pageH: number; cursor?: CKey[]; clicks?: number[]; cursorFrom?: number; cursorTo?: number; children: React.ReactNode;
}> = ({keys, pageH, cursor, clicks = [], cursorFrom = -1e9, cursorTo = 1e9, children}) => {
  const f = useCurrentFrame();
  const {S, tx, ty} = cam(f, keys, pageH);
  const scrollY = -ty / S;
  const band = Math.min(1, Math.max(0, scrollY / 20)) * interpolate(S, [1, 1.06], [1, 0], clamp);
  let cur: React.ReactNode = null;
  const ripples: React.ReactNode[] = [];
  if (cursor && cursor.length) {
    const ks = sortKeys(cursor);
    const opt = {...clamp, easing: Easing.inOut(Easing.cubic)};
    const px = interpolate(f, ks.map((k) => k.f), ks.map((k) => k.x), opt);
    const py = interpolate(f, ks.map((k) => k.f), ks.map((k) => k.y), opt);
    const sx = tx + px * S;
    const sy = ty + py * S;
    let press = 0;
    for (const c of clicks) {
      press = Math.max(press, interpolate(f, [c - 3, c, c + 5], [0, 1, 0], clamp));
      if (f >= c && f < c + 20) {
        const p = (f - c) / 20;
        ripples.push(
          <div key={c} style={{position: 'absolute', left: sx - 8 - 30 * p, top: sy - 8 - 30 * p, width: 16 + 60 * p, height: 16 + 60 * p,
            borderRadius: '50%', border: `3px solid ${C.teal}`, opacity: 0.8 * (1 - p)}} />,
        );
      }
    }
    const op = ease(f, cursorFrom, 8) * (1 - ease(f, cursorTo, 8));
    cur = <CursorIcon x={sx} y={sy} press={press} opacity={op} />;
  }
  return (
    <div style={{position: 'relative', width: VW, height: VH, overflow: 'hidden', background: '#F6F7F9'}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: VW, height: pageH, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${S})`}}>
        {children}
      </div>
      <div style={{position: 'absolute', left: 0, top: 0, right: 0, height: 60, background: '#F6F7F9', opacity: band}} />
      {ripples}
      {cur}
    </div>
  );
};

/** An image placed at page coordinates [x1, y1, x2, y2]. */
export const P: React.FC<{src: string; r: [number, number, number, number]; opacity?: number}> = ({src, r, opacity = 1}) => (
  <Img src={staticFile(src)} style={{position: 'absolute', left: r[0], top: r[1], width: r[2] - r[0], height: r[3] - r[1], opacity}} />
);

// Page-space positions of 2x crops (measured in the live app, which sits 68 px lower since the tab bar was added).
const CARD1 = {x: 173, y: 694, s: 690 / 1288};
const c1 = (x1: number, y1: number, x2: number, y2: number): [number, number, number, number] =>
  [CARD1.x + x1 * CARD1.s, CARD1.y + y1 * CARD1.s, CARD1.x + x2 * CARD1.s, CARD1.y + y2 * CARD1.s];
// v5 tiles: the card column (page x 155.8–882.7) at ~1.39x, captured after the full arithmetic was added.
const TX0 = 155.77;
const TX1 = 882.69;

export const ResultsLayers: React.FC<{open: number}> = ({open}) => (
  <>
    <P src="demo2/page_results.jpg" r={[0, 0, 1512, 1433]} opacity={1 - open} />
    <P src="v5/bk_open.jpg" r={[0, 0, 1512, 2561]} opacity={open} />
    <P src="demo2/header.png" r={[160, 520, 1346, 682]} />
    <P src="demo2/card1.png" r={[173, 694, 863, 1193]} />
    <P src="demo2/map.png" r={[926, 686, 1334, 1198]} />
    <P src="v5/bk_arith.png" r={[TX0, 1160, TX1, 1961]} opacity={open} />
  </>
);

const PageFrame: React.FC<{children: React.ReactNode; y?: number}> = ({children, y = 104}) => (
  <div style={{position: 'absolute', left: (1920 - VW) / 2, top: y}}>
    <Browser w={VW} h={VH} url="carefinder-india · Databricks App">{children}</Browser>
  </div>
);

const Callout: React.FC<{at: number; color: string; children: React.ReactNode; size?: number}> = ({at, color, children, size = 22}) => {
  const p = usePop(at, 14);
  const f = useCurrentFrame();
  return (
    <div style={{opacity: ease(f, at, 6), transform: `translateY(${(1 - p) * 14}px) scale(${0.9 + 0.1 * p})`, transformOrigin: 'left center',
      background: color, color: '#04161A', fontSize: size, fontWeight: 800, padding: '7px 14px', borderRadius: 10, whiteSpace: 'nowrap',
      boxShadow: '0 8px 24px rgba(0,0,0,0.25)'}}>
      {children}
    </div>
  );
};

// End of S3 = start of S4, so the cut between them is invisible.
const HANDOFF = {x: 756, y: 945, z: 1};

// ---------------- S3: live demo, part 1 (search) ----------------
export const S3Demo: React.FC = () => {
  const id = 's3_demo';
  const f = useCurrentFrame();
  const t = (p: string, o?: {nth?: number; end?: boolean; offset?: number}) => cue(id, p, o);
  const tTitle = t('CareFinder');
  const tPick = t('Pick');
  const tDial = t('dialysis');
  const tType = t('Type');
  const tBakh = t('Bakhtiyarpur');
  const tIsnt = t('No hospital');
  const tPost = t("India Post's");
  const tHundred = t('hundred thousand');
  const tOffices = t('offices', {end: true});
  const tFind = t('Find care');
  const tEvery = t('Of a thousand');
  const tMap = t('map the best');
  const tProb = t('probability');
  const tInt = t('interval');
  const tQuotes = t('quotes');
  const end = sceneLen(id);

  const titleP = usePop(tTitle - 8, 13);
  const browserIn = ease(f, tPick - 18, 18);
  const titleOut = easeIO(f, tPick - 20, 14);

  const clickSel = tPick + 6;
  const clickOpt = tDial + 4;
  const clickInput = tType + 4;
  const typeFrom = tBakh - 3;
  const typeTo = tBakh + 18;
  const clickFind = tFind + 4;
  const swap = clickFind + 8;

  const dropOpen = f >= clickSel + 1 && f < clickOpt + 2;
  const focused = f >= clickInput;
  const typed = interpolate(f, [typeFrom, typeTo], [0, 1], clamp);
  const results = interpolate(f, [swap, swap + 6], [0, 1], clamp);
  const press = interpolate(f, [clickFind - 2, clickFind + 1, clickFind + 6], [0, 1, 0], clamp);
  const caretOn = Math.floor(f / 8) % 2 === 0 || (f > typeFrom && f < typeTo);
  const textW = 132 * typed;

  const keys: Key[] = [
    {f: 0, x: 756, y: 402, z: 1},
    {f: tPick - 4, x: 756, y: 402, z: 1},
    {f: tPick + 12, x: 620, y: 400, z: 1.3},
    {f: tIsnt, x: 700, y: 400, z: 1.3},
    {f: tIsnt + 16, x: 760, y: 420, z: 1.12},
    {f: tFind - 10, x: 760, y: 420, z: 1.12},
    {f: tFind + 3, x: 980, y: 390, z: 1.25},
    {f: swap, x: 980, y: 390, z: 1.25},
    {f: swap + 1, x: 756, y: 402, z: 1},
    {f: tEvery - 6, x: 756, y: 402, z: 1},
    {f: tEvery + 10, x: 756, y: 640, z: 1.05},
    {f: tMap - 2, x: 756, y: 640, z: 1.05},
    {f: tMap + 12, x: 980, y: 900, z: 1.1},
    {f: tProb - 6, x: 980, y: 900, z: 1.1},
    {f: tProb + 10, x: 540, y: 900, z: 1.32},
    {f: tQuotes + 10, x: 540, y: 900, z: 1.32},
    {f: end, ...HANDOFF},
  ];
  const cursor: CKey[] = [
    {f: tPick - 10, x: 760, y: 600},
    {f: clickSel - 2, x: 404, y: 338},
    {f: clickOpt - 3, x: 234, y: 377},
    {f: clickInput - 2, x: 880, y: 338},
    {f: tIsnt, x: 880, y: 338},
    {f: tIsnt + 12, x: 1000, y: 410},
    {f: clickFind - 2, x: 1229, y: 337},
    {f: swap + 4, x: 1229, y: 337},
    {f: tEvery, x: 1300, y: 560},
  ];

  return (
    <AbsoluteFill>
      <Bg />
      <Chapter n="02" label="Live demo" />
      {f < tPick + 4 && (
        <AbsoluteFill style={{display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 1 - titleOut,
          transform: `translateY(${-titleOut * 120}px) scale(${1 - 0.15 * titleOut})`}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 34, transform: `scale(${0.85 + 0.15 * titleP})`, opacity: ease(f, tTitle - 8, 8)}}>
            <Logo size={140} />
            <div style={{fontSize: 136, fontWeight: 900, letterSpacing: -5}}>CareFinder <span style={{color: C.tealSoft}}>India</span></div>
          </div>
        </AbsoluteFill>
      )}

      <div style={{opacity: browserIn, transform: `translateY(${(1 - browserIn) * 260}px) perspective(2000px) rotateX(${(1 - browserIn) * 14}deg)`, transformOrigin: 'center top'}}>
        <PageFrame>
          <Viewport keys={keys} pageH={1433} cursor={cursor} clicks={[clickSel, clickOpt, clickInput, clickFind]} cursorFrom={tPick - 10} cursorTo={tEvery + 6}>
            <div style={{position: 'absolute', inset: 0, opacity: 1 - results}}>
              <P src="demo2/home.jpg" r={[0, 0, 1512, 805]} />
              {!focused && (
                <>
                  <P src="demo2/formL.png" r={[173, 263, 753, 437]} />
                  <P src="demo2/formR.png" r={[753, 263, 1333, 437]} />
                </>
              )}
              {focused && (
                <>
                  <P src="demo2/typedL.png" r={[173, 263, 753, 437]} />
                  <P src="demo2/typedR.png" r={[753, 263, 1333, 437]} />
                  <div style={{position: 'absolute', left: 638 + textW, top: 322, width: 776 - 638 - textW, height: 32, background: '#FFFFFF'}} />
                  {typed < 1 && caretOn && <div style={{position: 'absolute', left: 640 + textW, top: 327, width: 1.6, height: 22, background: '#0F172A'}} />}
                </>
              )}
              <div style={{position: 'absolute', left: 1146, top: 316, width: 166, height: 42, borderRadius: 12, background: '#000', opacity: 0.18 * press}} />
              {dropOpen && <P src="demo2/dropdown.png" r={[173, 263, 753, 663]} />}
            </div>
            <div style={{position: 'absolute', inset: 0, opacity: results}}>
              <ResultsLayers open={0} />
              <Box r={[553, 576, 752, 611]} s={1} at={tEvery + 2} until={tMap} color={C.teal} radius={18} pad={5} label="1,052 mention dialysis" side="bottom" />
              <Box r={[927, 690, 1333, 1190]} s={1} at={tMap + 4} until={tProb - 2} color={C.teal} radius={8} pad={4} label="the best 5, on a map" side="top" />
              <Box r={c1(310, 152, 560, 335)} s={1} at={tProb} until={tInt - 2} color={C.teal} radius={14} pad={4} label="P(offers dialysis | record)" side="bottom" />
              <Box r={c1(326, 262, 545, 292)} s={1} at={tInt} until={tQuotes - 2} color={C.amber} radius={8} pad={4} label="90% interval" side="bottom" />
              <Box r={c1(30, 400, 1258, 620)} s={1} at={tQuotes} color={C.teal} radius={10} pad={6} label="Quoted from its own record" side="topright" />
            </div>
          </Viewport>
        </PageFrame>
      </div>

      {f >= tIsnt - 4 && f < tFind + 20 && (
        <div style={{position: 'absolute', left: 110, top: 640, opacity: ease(f, tIsnt, 10) * (1 - easeIO(f, tFind + 2, 10))}}>
          <Glass style={{width: 640, padding: '24px 28px', background: 'rgba(6,20,24,0.94)'}}>
            <div style={{fontSize: 19, fontWeight: 800, letterSpacing: 3, color: C.muted, marginBottom: 14}}>LOCATING THE PATIENT</div>
            {[
              {at: tIsnt, icon: 'hospital', color: C.red, title: 'Hospital records', right: <Pill icon="x" color={C.red} size={20}>no “Bakhtiyarpur”</Pill>},
              {at: tPost, icon: 'mail', color: C.amber, title: 'India Post directory',
                right: <span style={{fontSize: 30, fontWeight: 900, color: C.amber}}><Counter to={100000} at={tHundred} dur={tOffices - tHundred + 4} suffix="+" /></span>},
              {at: tOffices, icon: 'pin', color: C.tealSoft, title: 'Bakhtiyarpur · Patna district', right: <Pill icon="check" color={C.tealSoft} size={20}>±3 km</Pill>},
            ].map((r, i) => (
              <Appear key={i} at={r.at} dx={30} dy={0}>
                <div style={{display: 'flex', alignItems: 'center', gap: 16, padding: '12px 0', borderTop: i ? '1px solid rgba(255,255,255,0.08)' : undefined}}>
                  <div style={{width: 48, height: 48, borderRadius: 12, background: `${r.color}22`, border: `2px solid ${r.color}66`, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                    <Icon name={r.icon} size={26} color={r.color} />
                  </div>
                  <div style={{flex: 1, fontSize: 27, fontWeight: 800, color: C.text}}>{r.title}</div>
                  {r.right}
                </div>
              </Appear>
            ))}
          </Glass>
        </div>
      )}
      <Captions id={id} from={1.2} />
    </AbsoluteFill>
  );
};

// ---------------- S4: live demo, part 2 (why this ranking, and the arithmetic) ----------------
export const S4Results: React.FC = () => {
  const id = 's4_results';
  const f = useCurrentFrame();
  const t = (p: string, o?: {nth?: number; end?: boolean}) => cue(id, p, o);
  const end = sceneLen(id);
  const tSam = t('Samarpan');
  const tThree = t('three fields');
  const tSite = t('own website');
  const tFlags = t('no red flags');
  const tNinety = t('ninety-nine');
  const tNear = t('The nearest');
  const tOnce = t('once');
  const tEleven = t('eleven');
  const tWhy = t('says why');
  const tOpen = t('Open the card');
  const tArith = t('arithmetic');
  const clickExp = tOpen + 6;
  const open = interpolate(f, [clickExp + 2, clickExp + 7], [0, 1], clamp);
  const CARD = {x: 518, y: 943, z: 1.5};

  const keys: Key[] = [
    {f: 0, ...HANDOFF},
    {f: tSam - 2, ...HANDOFF},
    {f: tSam + 14, ...CARD},
    {f: tNear - 4, ...CARD},
    {f: tNear + 12, x: 753, y: 700, z: 1.25},
    {f: tOpen - 4, x: 753, y: 700, z: 1.25},
    {f: tOpen + 6, x: 756, y: 1110, z: 1},
    {f: clickExp + 3, x: 756, y: 1110, z: 1},
    {f: clickExp + 18, x: 520, y: 1700, z: 1.5},
    {f: end, x: 520, y: 1720, z: 1.52},
  ];
  const cursor: CKey[] = [
    {f: tOpen - 2, x: 760, y: 1120},
    {f: clickExp - 2, x: 500, y: 1221},
    {f: end, x: 500, y: 1221},
  ];

  return (
    <AbsoluteFill>
      <Bg />
      <Chapter n="02" label="Live demo" />
      <PageFrame>
        <Viewport keys={keys} pageH={2561} cursor={cursor} clicks={[clickExp]} cursorFrom={tOpen} cursorTo={clickExp + 12}>
          <ResultsLayers open={open} />
          <Box r={c1(118, 30, 745, 125)} s={1} at={tSam} until={tThree} label="#1" side="right" radius={12} />
          <Box r={c1(30, 400, 1258, 620)} s={1} at={tThree} until={tSite - 1} label="3 fields of its own record" side="topright" />
          {[0, 1, 2].map((i) => {
            const at = tThree + 2 + i * 4;
            const p = ease(f, at, 6);
            const [x, y] = c1(1200, 428 + i * 72, 0, 0);
            return (
              <div key={i} style={{position: 'absolute', left: x, top: y, width: 24, height: 24, borderRadius: 12, background: C.green,
                display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: p * (1 - ease(f, tSite - 1, 6)), transform: `scale(${0.5 + 0.5 * p})`}}>
                <Icon name="check" size={16} color="white" sw={3.4} />
              </div>
            );
          })}
          <Box r={c1(36, 790, 674, 842)} s={1} at={tSite} until={tFlags - 1} radius={16} pad={4} label="its own website" side="right" />
          <Box r={c1(38, 700, 1250, 775)} s={1} at={tFlags} until={tNinety - 1} color={C.green} radius={12} pad={4} />
          <Box r={c1(310, 152, 560, 335)} s={1} at={tNinety} until={tNear - 2} color={C.green} radius={14} pad={4} label="≥ 0.99" side="bottom" />
          <Box r={c1(918, 36, 1250, 100)} s={1} at={tNinety + 3} until={tNear - 2} color={C.green} radius={22} pad={4} />
          <Box r={[173, 630, 1333, 674]} s={1} at={tNear + 4} until={tOpen - 2} color={C.blue} radius={10} pad={4} />
          <div style={{position: 'absolute', left: 190, top: 690, display: 'flex', gap: 12, opacity: 1 - easeIO(f, tOpen - 4, 8)}}>
            <Callout at={tNear + 8} color={C.tealSoft}>Satyarthi Hospital · 31 km, the nearest</Callout>
            <Callout at={tOnce} color={C.amber}>dialysis once, inside a list</Callout>
            <Callout at={tEleven} color={'#FCA5A5'}>P = 0.11</Callout>
            <Callout at={tWhy} color={'#CBD5E1'}>and it says why</Callout>
          </div>
          <Box r={[184, 1564, 852, 1724]} s={1} at={tArith - 4} color={C.teal} radius={8} pad={6} label="each field's learned factor" side="topright" />
          <Box r={[184, 1836, 852, 1893]} s={1} at={tArith + 8} color={C.amber} radius={8} pad={6} />
        </Viewport>
      </PageFrame>
      <Captions id={id} />
    </AbsoluteFill>
  );
};

// ---------------- S5: live demo, part 3 (a PIN code, a red flag and a wide interval) ----------------
const PUNE_CARD = {x: 518, y: 2637, z: 1.45};
export const S5Pune: React.FC = () => {
  const id = 's5_pune';
  const f = useCurrentFrame();
  const t = (p: string, o?: {nth?: number; end?: boolean}) => cue(id, p, o);
  const end = sceneLen(id);
  const tPin = t('A PIN code');
  const tNear = t('burn care near');
  const tCard = t('Card four');
  const tList = t('lists burns');
  const tNone = t('none of its');
  const tPoint = t('point four three');
  const tResult = t('Result');
  const tInt = t('interval six');
  const tLow = t('Marked Low');
  const clickChip = tPin + 5;
  const swap = clickChip + 6;
  const clickExp = tResult - 4;
  const open = interpolate(f, [clickExp + 2, clickExp + 7], [0, 1], clamp);
  const pune = interpolate(f, [swap, swap + 6], [0, 1], clamp);

  const keys: Key[] = [
    {f: 0, x: 756, y: 640, z: 1.1},
    {f: clickChip, x: 756, y: 560, z: 1.1},
    {f: swap + 1, x: 756, y: 560, z: 1.1},
    {f: tNear + 10, x: 756, y: 640, z: 1.1},
    {f: tCard - 4, x: 756, y: 640, z: 1.1},
    {f: tCard + 14, ...PUNE_CARD},
    {f: clickExp - 4, ...PUNE_CARD},
    {f: clickExp + 12, x: 518, y: 3250, z: 1.45},
    {f: tInt - 4, x: 518, y: 3250, z: 1.45},
    {f: tInt + 10, ...PUNE_CARD},
    {f: end, ...PUNE_CARD},
  ];
  const cursor: CKey[] = [
    {f: 0, x: 980, y: 560},
    {f: clickChip - 2, x: 727, y: 466},
    {f: swap + 6, x: 727, y: 466},
    {f: clickExp - 8, x: 600, y: 2860},
    {f: clickExp + 2, x: 500, y: 2864},
    {f: end, x: 500, y: 2864},
  ];
  return (
    <AbsoluteFill>
      <Bg />
      <Chapter n="02" label="Live demo · a PIN code" />
      <PageFrame>
        <Viewport keys={keys} pageH={3861} cursor={cursor} clicks={[clickChip, clickExp]} cursorFrom={0} cursorTo={clickExp + 12}>
          <div style={{position: 'absolute', inset: 0, opacity: 1 - pune}}>
            <ResultsLayers open={0} />
          </div>
          <div style={{position: 'absolute', inset: 0, opacity: pune}}>
            <P src="v5/pune_page.jpg" r={[0, 0, 1512, 3261]} opacity={1 - open} />
            <P src="v5/pune_open.jpg" r={[0, 0, 1512, 3861]} opacity={open} />
            <P src="v5/pune_top_L.png" r={[0, 0, 756, 861]} />
            <P src="v5/pune_top_R.png" r={[756, 0, 1512, 861]} />
            <P src="v5/ycm_card_closed.png" r={[TX0, 2460, TX1, 3261]} opacity={1 - open} />
            <P src="v5/ycm_card_open.png" r={[TX0, 2460, TX1, 3261]} opacity={open} />
            <P src="v5/ycm_arith.png" r={[TX0, 3060, TX1, 3861]} opacity={open} />
            <Box r={[173, 576, 521, 610]} s={1} at={tNear} until={tCard - 2} color={C.teal} radius={18} pad={5} label="located by PIN code, ±2 km" side="bottom" />
            <Box r={[673, 2456, 843, 2493]} s={1} at={tCard + 6} until={tList} color={C.red} radius={18} pad={4} />
            <Box r={[192, 2657, 845, 2728]} s={1} at={tList} until={tNone - 1} color={C.amber} radius={10} pad={4} label="once, in a long list" side="topright" />
            <Box r={[192, 2742, 845, 2791]} s={1} at={tNone} until={clickExp} color={C.red} radius={12} pad={4} label="learned: odds ×0.43" side="bottom" />
            <Box r={[188, 3118, 850, 3274]} s={1} at={clickExp + 10} until={tInt - 4} color={C.teal} radius={8} pad={6} />
            <Box r={[188, 3336, 850, 3414]} s={1} at={tResult + 4} until={tInt - 4} color={C.amber} radius={8} pad={6} label="0.49" side="topright" />
            <Box r={[337, 2517, 474, 2618]} s={1} at={tInt + 8} color={C.amber} radius={12} pad={4} label="90% interval 0.06–0.73" side="bottom" />
            <Box r={[673, 2456, 843, 2493]} s={1} at={tLow} color={C.red} radius={18} pad={4} label="call ahead" side="right" />
          </div>
        </Viewport>
      </PageFrame>
      <Captions id={id} />
    </AbsoluteFill>
  );
};

// ---------------- S10: the planner tab ----------------
export const S10Plan: React.FC = () => {
  const id = 's10_plan';
  const f = useCurrentFrame();
  const t = (p: string, o?: {nth?: number; end?: boolean}) => cue(id, p, o);
  const end = sceneLen(id);
  const tTab = t('second tab');
  const tPick = t('Pick a service');
  const tNeed = t('need indicator');
  const tNfhs = t('NFHS-5');
  const tFor = t('For C-sections');
  const tPlace = t('we place');
  const tAsk = t('is a High-confidence');
  const tSeventeen = t('seventeen');
  const tRed = t('Red circles');
  const tSized = t('sized by need');
  const tKatihar = t('Katihar');
  const clickTab = tTab + 2;
  const dropAt = tNeed + 2;
  const dropOff = tFor - 2;
  const keys: Key[] = [
    {f: 0, x: 756, y: 402, z: 1},
    {f: tPick - 4, x: 756, y: 402, z: 1},
    {f: tPick + 10, x: 756, y: 390, z: 1.15},
    {f: tNeed, x: 756, y: 390, z: 1.15},
    {f: tNeed + 10, x: 1080, y: 520, z: 1.25},
    {f: tFor - 4, x: 1080, y: 520, z: 1.25},
    {f: tFor + 8, x: 756, y: 402, z: 1.05},
    {f: tPlace + 2, x: 756, y: 402, z: 1.05},
    {f: tPlace + 14, x: 1073, y: 810, z: 1.3},
    {f: tSeventeen - 6, x: 1073, y: 810, z: 1.3},
    {f: tSeventeen + 6, x: 470, y: 476, z: 1.45},
    {f: tRed - 4, x: 470, y: 476, z: 1.45},
    {f: tRed + 10, x: 1073, y: 840, z: 1.3},
    {f: tKatihar - 6, x: 1073, y: 840, z: 1.3},
    {f: tKatihar + 8, x: 462, y: 700, z: 1.45},
    {f: end, x: 462, y: 700, z: 1.47},
  ];
  const cursor: CKey[] = [
    {f: 0, x: 640, y: 300},
    {f: clickTab - 2, x: 450, y: 190},
    {f: dropAt - 2, x: 1100, y: 372},
    {f: tFor + 6, x: 1250, y: 470},
  ];
  const tabOn = f >= clickTab + 1;
  const drop = f >= dropAt && f < dropOff;
  return (
    <AbsoluteFill>
      <Bg />
      <Chapter n="03" label="Plan coverage · for planners" />
      <PageFrame>
        <Viewport keys={keys} pageH={1151} cursor={cursor} clicks={[clickTab, dropAt]} cursorFrom={2} cursorTo={tFor + 10}>
          <div style={{opacity: tabOn ? 1 : 0}}>
            <P src="plan2/page_full.jpg" r={[0, 0, 1512, 1151]} />
            <P src="plan2/kpiL.png" r={[173, 422, 753, 531]} />
            <P src="plan2/kpiR.png" r={[753, 422, 1333, 531]} />
            <P src="plan2/list.png" r={[173, 578, 749, 986]} />
            <P src="plan2/map.png" r={[813, 545, 1333, 1045]} />
            {drop && <P src="v5/plan_dropdown_R.png" r={[756, 0, 1512, 861]} />}
          </div>
          {!tabOn && <P src="demo2/page_results.jpg" r={[0, 0, 1512, 1433]} />}
          <Box r={[345, 176, 553, 206]} s={1} at={clickTab} until={tPick} color={C.teal} radius={8} pad={4} />
          <Box r={[173, 352, 1333, 392]} s={1} at={tPick} until={tNeed} color={C.teal} radius={10} pad={5} label="service · state · need indicator" side="bottom" />
          <Box r={[866, 392, 1333, 680]} s={1} at={tNfhs} until={dropOff} color={C.amber} radius={10} pad={4} label="NFHS-5: National Family Health Survey 2019–21, every district" side="bottom" />
          <Box r={[173, 352, 849, 392]} s={1} at={tFor} until={tPlace} color={C.teal} radius={10} pad={5} />
          <Box r={[813, 545, 1333, 1045]} s={1} at={tPlace + 10} until={tSeventeen - 6} color={C.teal} radius={6} pad={2} />
          <div style={{position: 'absolute', left: 840, top: 570, display: 'flex', flexDirection: 'column', gap: 8, opacity: 1 - easeIO(f, tSeventeen - 8, 8)}}>
            <Callout at={tPlace + 12} color={C.tealSoft} size={17}>each circle = a district, placed at the centre of its post offices</Callout>
            <Callout at={tAsk} color={'#CBD5E1'} size={17}>covered = a High-confidence hospital, P(arrive ≤ 2 h) ≥ 50%</Callout>
          </div>
          <Box r={[173, 422, 453, 531]} s={1} at={tSeventeen} until={tRed - 2} color={C.red} radius={14} pad={4} label="17 of 38 districts: no" side="bottom" />
          <Box r={[813, 545, 1333, 1045]} s={1} at={tRed + 6} until={tSized} color={C.red} radius={6} pad={2} />
          <Box r={[811, 1062, 1330, 1122]} s={1} at={tSized} until={tKatihar - 2} color={C.amber} radius={8} pad={4} label="bigger circle = more need" side="top" />
          <Box r={[180, 598, 742, 672]} s={1} at={tKatihar + 4} color={C.amber} radius={12} pad={4} label="Katihar: 4.0% C-section births · nearest 94 km" side="top" />
        </Viewport>
      </PageFrame>
      <Captions id={id} />
    </AbsoluteFill>
  );
};
