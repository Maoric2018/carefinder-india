import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {
  Appear, Bg, Box, Browser, C, Camera, Captions, Chapter, Counter, Glass, Icon, Logo, PhotoBg, Pill,
  clamp, cue, ease, easeIO, sceneLen, usePop,
} from './lib';

// ---------------- S11: close (with the Genie space) ----------------
export const S11Close: React.FC = () => {
  const id = 's11_close';
  const f = useCurrentFrame();
  const len = sceneLen(id);
  const logo = usePop(0, 13);
  const chips = ['Notebooks', 'Delta tables', 'Unity Catalog', 'Databricks App', 'Genie'];
  const chipAt = cue(id, 'Built');
  const genieAt = cue(id, 'Genie space');
  const g = usePop(genieAt - 4, 15);
  const scroll = interpolate(f, [genieAt + 10, len], [0, 150], {...clamp});
  return (
    <AbsoluteFill>
      <Bg grid={false} />
      <PhotoBg src="img/hero_map.png" len={len} opacity={0.28} from={1.08} to={1.0} origin="70% 50%" />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 45%, rgba(5,18,22,0.55), rgba(5,18,22,0.92) 75%)'}} />
      <AbsoluteFill style={{display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 70}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 26, transform: `scale(${0.8 + 0.2 * logo})`, opacity: ease(f, 0, 10)}}>
          <Logo size={92} />
          <div style={{fontSize: 92, fontWeight: 900, letterSpacing: -4}}>
            CareFinder <span style={{color: C.tealSoft}}>India</span>
          </div>
        </div>
        <div style={{marginTop: 22, display: 'flex', gap: 28, alignItems: 'baseline'}}>
          <Appear at={cue(id, 'Every answer')}>
            <div style={{fontSize: 44, fontWeight: 800, color: C.text, letterSpacing: -1}}>Every answer cited.</div>
          </Appear>
          <Appear at={cue(id, 'every number')}>
            <div style={{fontSize: 44, fontWeight: 800, color: C.tealSoft, letterSpacing: -1}}>Every number with its uncertainty.</div>
          </Appear>
        </div>
        <div style={{marginTop: 34, opacity: ease(f, genieAt - 4, 10), transform: `translateY(${(1 - g) * 60}px) scale(${0.94 + 0.06 * g})`}}>
          <Browser w={1150} h={430} url="Genie space · CareFinder India: find the right care" dark>
            <Img src={staticFile('v5/genie_wide.png')} style={{position: 'absolute', left: 0, top: 6 - scroll, width: 1150}} />
          </Browser>
        </div>
        <Appear at={chipAt} style={{marginTop: 30}}>
          <div style={{fontSize: 28, fontWeight: 700, color: C.muted, textAlign: 'center', letterSpacing: 1}}>
            Built entirely on <span style={{color: C.text}}>Databricks Free Edition</span>
          </div>
        </Appear>
        <div style={{display: 'flex', gap: 14, marginTop: 16}}>
          {chips.map((c, i) => (
            <Appear key={c} at={chipAt + i * 3} dy={16}>
              <Pill size={22} color={C.tealSoft}>{c}</Pill>
            </Appear>
          ))}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
