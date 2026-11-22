import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {
  Appear, Bg, C, Captions, Chapter, Counter, Glass, Icon, Logo, PhotoBg, Pill, Box, Shot, SpokenLine,
  clamp, cue, ease, easeIO, sceneLen, usePop,
} from './lib';

// ---------------- S1: the hook ----------------
export const S1Hook: React.FC = () => {
  const id = 's1_hook';
  const f = useCurrentFrame();
  const len = sceneLen(id);
  const fadeIn = interpolate(f, [0, 22], [0, 1], clamp);
  const q = cue(id, 'Where');
  const dim = interpolate(f, [q - 10, q + 10], [0, 1], clamp);
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <AbsoluteFill style={{opacity: fadeIn}}>
        <PhotoBg src="img/health_worker.png" len={len} from={1.03} to={1.13} origin="70% 40%" flip />
        <AbsoluteFill style={{background: `linear-gradient(90deg, rgba(3,12,15,${0.88 + 0.06 * dim}) 0%, rgba(3,12,15,${0.62 + 0.2 * dim}) 38%, rgba(3,12,15,0.05) 68%)`}} />
        <AbsoluteFill style={{background: 'linear-gradient(0deg, rgba(3,12,15,0.85) 0%, transparent 32%)'}} />
      </AbsoluteFill>

      <div style={{position: 'absolute', left: 120, top: 210, display: 'flex', flexDirection: 'column', gap: 22, alignItems: 'flex-start'}}>
        <Appear at={cue(id, 'health worker')} dx={-30} dy={0}>
          <div style={{fontSize: 24, fontWeight: 700, letterSpacing: 4, color: 'rgba(241,245,249,0.75)', textTransform: 'uppercase'}}>
            A community health worker
          </div>
        </Appear>
        <Appear at={cue(id, 'rural Bihar')} dx={-30} dy={0}>
          <Pill icon="pin" size={34}>Bakhtiyarpur, Bihar</Pill>
        </Appear>
        <Appear at={cue(id, 'dialysis')} dx={-30} dy={0}>
          <Pill icon="heart" size={34} color={C.amber}>Patient needs dialysis</Pill>
        </Appear>
      </div>

      <div style={{position: 'absolute', left: 120, top: 520, width: 1050}}>
        <SpokenLine id={id} phrase="Where should she send him?" size={96} />
        <div style={{height: 18}} />
        <SpokenLine id={id} phrase="And why should she trust the answer?" size={96} accent={['trust']} />
      </div>
      <Captions id={id} until={5} />
    </AbsoluteFill>
  );
};

// ---------------- S2: the data problem ----------------
const Stat: React.FC<{at: number; value: React.ReactNode; color: string; icon: string; text: string}> = ({at, value, color, icon, text}) => {
  const p = usePop(at, 16);
  const f = useCurrentFrame();
  return (
    <div style={{opacity: ease(f, at, 8), transform: `translateX(${(1 - p) * 80}px)`}}>
      <Glass accent={color} style={{width: 760, padding: '26px 34px', display: 'flex', alignItems: 'center', gap: 30}}>
        <div style={{width: 72, height: 72, borderRadius: 18, background: `${color}22`, border: `2px solid ${color}66`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0}}>
          <Icon name={icon} size={38} color={color} />
        </div>
        <div style={{fontSize: 62, fontWeight: 900, color, minWidth: 240, letterSpacing: -2, whiteSpace: 'nowrap'}}>{value}</div>
        <div style={{fontSize: 29, fontWeight: 600, color: C.text, lineHeight: 1.25}}>{text}</div>
      </Glass>
    </div>
  );
};

export const S2Data: React.FC = () => {
  const id = 's2_data';
  const f = useCurrentFrame();
  const len = sceneLen(id);
  const claimAt = cue(id, 'But a page');
  const checkAt = cue(id, 'Checked');
  const proofAt = cue(id, 'proof');
  const stampP = usePop(proofAt, 11);
  return (
    <AbsoluteFill>
      <Bg grid={false} />
      <PhotoBg src="img/records_noise.png" len={len} opacity={0.5} from={1.12} to={1.02} />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 30% 50%, rgba(5,18,22,0.92) 0%, rgba(5,18,22,0.55) 60%, rgba(5,18,22,0.3) 100%)'}} />
      <Chapter n="01" label="The data" />

      {/* left: the dataset */}
      <div style={{position: 'absolute', left: 120, top: 250, width: 860}}>
        <Appear at={cue(id, 'Virtue')}>
          <div style={{fontSize: 26, fontWeight: 800, letterSpacing: 4, color: C.tealSoft}}>VIRTUE FOUNDATION DATASET</div>
        </Appear>
        <Appear at={cue(id, 'lists')}>
          <div style={{fontSize: 210, fontWeight: 900, letterSpacing: -9, lineHeight: 1, marginTop: 12,
            backgroundImage: 'linear-gradient(180deg, #FFFFFF 30%, #8FE9DC)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent'}}>
            <Counter to={10088} at={cue(id, 'lists')} dur={cue(id, 'facilities') - cue(id, 'lists') + 6} />
          </div>
        </Appear>
        <Appear at={cue(id, 'Indian')}>
          <div style={{fontSize: 40, fontWeight: 700, color: C.text, marginTop: 10}}>Indian health facility records</div>
        </Appear>
        <Appear at={cue(id, 'scraped')}>
          <div style={{display: 'flex', gap: 14, marginTop: 26}}>
            <Pill icon="globe" size={26} color={C.muted}>scraped from the web</Pill>
          </div>
        </Appear>
      </div>

      {/* right: a claim is not proof */}
      <div style={{position: 'absolute', left: 1040, top: 270}}>
        <Appear at={claimAt} out={checkAt - 6} dx={60} dy={0}>
          <Glass style={{width: 720, padding: '34px 40px'}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 14, color: C.muted, fontSize: 22, fontWeight: 700, letterSpacing: 3}}>
              <Icon name="doc" size={26} color={C.muted} /> A FACILITY RECORD SAYS
            </div>
            <div style={{fontSize: 64, fontWeight: 800, marginTop: 18, color: C.text, letterSpacing: -1.5}}>“We offer dialysis.”</div>
            <div style={{marginTop: 30, display: 'flex', alignItems: 'center', gap: 18, opacity: ease(f, proofAt - 4, 8),
              transform: `scale(${0.7 + 0.3 * stampP}) rotate(${-4 * stampP}deg)`, transformOrigin: 'left center'}}>
              <div style={{border: `4px solid ${C.amber}`, color: C.amber, borderRadius: 12, padding: '8px 20px', fontSize: 38, fontWeight: 900, letterSpacing: 2}}>
                CLAIM ≠ PROOF
              </div>
            </div>
          </Glass>
        </Appear>
      </div>

      <div style={{position: 'absolute', left: 1040, top: 200, display: 'flex', flexDirection: 'column', gap: 26}}>
        {f >= checkAt - 2 && (
          <>
            <Appear at={checkAt} dy={0}>
              <div style={{fontSize: 24, fontWeight: 800, letterSpacing: 4, color: C.muted, marginBottom: 2}}>CHECKED AGAINST INDIA POST</div>
            </Appear>
            <Stat at={cue(id, 'one in ten')} color={C.amber} icon="pin" value="~1 in 10" text="map pins >90 km from the record's own city (checked against India Post PINs)" />
            <Stat at={cue(id, 'Seven hundred')} color={C.amber} icon="merge" value={<Counter to={772} at={cue(id, 'Seven hundred')} dur={20} />} text="records name 3+ other hospitals: likely merged pages" />
            <Stat at={cue(id, 'thirty-five')} color={C.red} icon="alert" value={<Counter to={35} at={cue(id, 'thirty-five')} dur={12} />} text="rows with shifted columns (corrupted)" />
          </>
        )}
      </div>
      <Captions id={id} />
    </AbsoluteFill>
  );
};

