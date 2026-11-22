import React from 'react';
import {AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {C, FPS, OVERLAP, PAD, SCENES, TOTAL, clamp, fontFamily, timing, type SceneId} from './lib';
import {S1Hook, S2Data} from './scenes1';
import {S3Demo, S4Results, S5Pune, S10Plan} from './demo';
import {S6Model, S7Odds, S8Checks, S9Access} from './method';
import {S11Close} from './scenes3';

const COMPONENTS: Record<SceneId, React.FC> = {
  s1_hook: S1Hook, s2_data: S2Data, s3_demo: S3Demo, s4_results: S4Results, s5_pune: S5Pune, s6_model: S6Model,
  s7_odds: S7Odds, s8_checks: S8Checks, s9_access: S9Access, s10_plan: S10Plan, s11_close: S11Close,
};

const SceneWrap: React.FC<{dur: number; first: boolean; last: boolean; cont?: boolean; children: React.ReactNode}> = ({dur, first, last, cont, children}) => {
  const f = useCurrentFrame();
  const fadeIn = first ? 1 : interpolate(f, [0, OVERLAP], [0, 1], clamp);
  const fadeOut = last ? interpolate(f, [dur - 26, dur - 2], [1, 0], clamp) : 1;
  const zoom = first || cont ? 1 : interpolate(f, [0, OVERLAP + 6], [1.035, 1], clamp);
  return (
    <AbsoluteFill style={{opacity: fadeIn * fadeOut, transform: `scale(${zoom})`}}>
      {children}
    </AbsoluteFill>
  );
};

const lastScene = SCENES[SCENES.length - 1];
const closeVoiceEnd = lastScene.from + PAD + Math.round(timing[lastScene.id].duration * FPS);

const musicVolume = (fr: number) => {
  const fadeIn = interpolate(fr, [0, 40], [0.0, 1], clamp);
  const fadeOut = interpolate(fr, [TOTAL - 50, TOTAL - 4], [1, 0], clamp);
  const lift = interpolate(fr, [closeVoiceEnd - 6, closeVoiceEnd + 14], [0.16, 0.36], clamp);
  return lift * fadeIn * fadeOut;
};

const Progress: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <div style={{position: 'absolute', left: 0, bottom: 0, height: 5, width: `${(f / TOTAL) * 100}%`,
      background: 'linear-gradient(90deg, #0F766E, #5EEAD4)', opacity: 0.85}} />
  );
};

export const Video: React.FC = () => (
  <AbsoluteFill style={{fontFamily, background: C.bg, color: C.text}}>
    {SCENES.map((sc, i) => {
      const Comp = COMPONENTS[sc.id];
      return (
        <Sequence key={sc.id} from={sc.from} durationInFrames={sc.dur} name={sc.id}>
          <SceneWrap dur={sc.dur} first={i === 0} last={i === SCENES.length - 1} cont={sc.id === 's4_results'}>
            <Comp />
          </SceneWrap>
          <Sequence from={PAD} name={`${sc.id} voice`}>
            <Audio src={staticFile(`audio/${sc.id}.mp3`)} />
          </Sequence>
        </Sequence>
      );
    })}
    <Audio src={staticFile('audio/music.mp3')} volume={musicVolume} />
    <Progress />
  </AbsoluteFill>
);
