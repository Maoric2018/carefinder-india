import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile} from 'remotion';
import {Captions, type SceneId} from './lib';

// The method scenes are Manim animations (video/manim/method_scenes.py), rendered at 1920x1080 and synced to the
// voiceover word timings (beats.json), so they start at the scene's frame 0. They are drawn slightly smaller and
// pinned to the top, so the captions have a band of their own at the bottom.
const SCALE = 0.885;
// The clip's flat background as Chrome decodes it, plus feathered edges, so the clip has no visible border.
const CLIP_BG = 'rgb(2,15,21)';
const FEATHER = 'linear-gradient(90deg, transparent, black 3%, black 97%, transparent), linear-gradient(180deg, transparent, black 3%, black 97%, transparent)';

const ManimScene: React.FC<{id: SceneId; clip: string}> = ({id, clip}) => (
  <AbsoluteFill style={{background: CLIP_BG}}>
    <div style={{position: 'absolute', left: (1920 * (1 - SCALE)) / 2, top: 8, width: 1920 * SCALE, height: 1080 * SCALE,
      WebkitMaskImage: FEATHER, maskImage: FEATHER, WebkitMaskComposite: 'source-in', maskComposite: 'intersect'}}>
      <OffthreadVideo src={staticFile(`manim/${clip}.mp4`)} muted style={{width: '100%', height: '100%'}} />
    </div>
    <Captions id={id} />
  </AbsoluteFill>
);

export const S6Model: React.FC = () => <ManimScene id="s6_model" clip="ModelScene" />;
export const S7Odds: React.FC = () => <ManimScene id="s7_odds" clip="OddsScene" />;
export const S8Checks: React.FC = () => <ManimScene id="s8_checks" clip="ChecksScene" />;
export const S9Access: React.FC = () => <ManimScene id="s9_access" clip="AccessScene" />;
