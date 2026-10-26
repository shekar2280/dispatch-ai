'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Bricolage_Grotesque, Instrument_Sans, Tiro_Devanagari_Hindi } from 'next/font/google';
import { Check, Menu, X } from 'lucide-react';

const fDisplay = Bricolage_Grotesque({ subsets: ['latin'], variable: '--font-display', display: 'swap' });
const fBody = Instrument_Sans({ subsets: ['latin'], variable: '--font-body', display: 'swap' });
const fDeva = Tiro_Devanagari_Hindi({ subsets: ['devanagari', 'latin'], weight: '400', variable: '--font-deva', display: 'swap' });

const BRAND = { name: 'Dispatch AI', logo: '/images/icon.png' };

const NAV = [
  { id: 'features', label: 'Overview' },
  { id: 'voice-reception', label: 'Voice AI' },
  { id: 'chamber-queue', label: 'OPD Queue' },
  { id: 'how-it-works', label: 'How It Works' },
];

const STATS: { value: number | string; prefix?: string; suffix?: string; label: string }[] = [
  { value: 'Voice', label: 'Reception over LiveKit and WebRTC' },
  { value: 'Live', label: 'Appointment and walk-in queues' },
  { value: 'Roles', label: 'Clinic membership and access controls' },
  { value: 'Usage', label: 'Voice budgets and call telemetry' },
];

const FEATURES = [
  {
    tag: 'OPD queue & clinic desk', title: 'One dashboard for your entire clinic', type: 'dashboard',
    body: 'Doctors track live patient arrival times, call next tokens into the consultation chamber, and view AI-flagged emergencies in a clean, distraction-free interface.'
  },
  {
    tag: 'Zero-keypad voice AI', title: 'Speaks your patients’ native language', type: 'voice',
    body: 'Patients never navigate annoying IVR menus or press phone keypads. The voice agent instantly detects English, Hindi, Hinglish, and regional accents to answer naturally.'
  },
  {
    tag: 'EHR capacity engine', title: 'Strict capacity & zero double bookings', type: 'calendar',
    body: 'Every booking cross-checks your doctor’s consultation hours, buffer times, and max daily patient limits with transactional locks before issuing a token.'
  },
  {
    tag: 'Call telemetry & audit', title: 'Actionable call transcripts & triage', type: 'telemetry',
    body: 'Inspect verbatim caller transcripts, audio recordings, and triage classifications. Track patient conversion rates from incoming ring to completed OPD consultation.'
  },
];

const STEPS = [
  {
    title: 'Patient dials your clinic number',
    body: 'Connect a configured Twilio number and LiveKit SIP route to the voice receptionist. Provider availability and your usage allowance determine call handling.'
  },
  {
    title: 'AI understands symptoms & checks schedule',
    body: 'The voice agent detects the patient’s language, gathers visit context, and queries open doctor consultation slots with sub-millisecond calendar verification.'
  },
  {
    title: 'Token locked & calendar synchronized',
    body: 'After the caller confirms the booking details, the appointment is saved to the clinic schedule and appears in the staff queue.'
  },
];

const MOCK_TRANSCRIPT = [
  { who: 'Patient', text: 'Namaste, can I get a consultation slot with Dr. Mehta for fever tomorrow?' },
  { who: 'Dispatch AI', text: 'Namaste! Dr. Mehta is available tomorrow at 09:30 AM or 10:15 AM. Which works best for you?' },
  { who: 'Patient', text: '10:15 AM works best for me.' },
  { who: 'Dispatch AI', text: 'Confirmed! Token #08 locked for 10:15 AM tomorrow with Dr. Mehta. SMS sent to your number.' },
];

const QUEUE = [
  { n: '#04', name: 'Ramesh Gupta', note: 'General Consultation · Fever', chip: 'In Chamber', active: true },
  { n: '#05', name: 'Sunita Devi', note: 'Follow-up · Blood Pressure', chip: 'Waiting (Room 1)' },
  { n: '#06', name: 'Amit Sharma', note: 'Consultation · Joint Pain', chip: 'Arrival in 5m' },
];

const WAVE = [0.35, 0.6, 0.9, 0.5, 0.75, 0.4, 0.95, 0.55, 0.3, 0.7, 0.85, 0.45];

function useInView<T extends HTMLElement>(threshold = 0.3) {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return { ref, seen };
}

function useCallSim() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep((s) => (s + 1) % (MOCK_TRANSCRIPT.length + 2)), 2400);
    return () => clearInterval(id);
  }, []);
  return { step, booked: step >= MOCK_TRANSCRIPT.length };
}

function CountUp({ to, active }: { to: number; active: boolean }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!active) return;
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min((t - t0) / 1600, 1);
      setN(Math.round((1 - Math.pow(1 - k, 3)) * to));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, to]);
  return <>{n}</>;
}

function Wave({ live = false }: { live?: boolean }) {
  return (
    <span className="dx-wave" data-live={live} aria-hidden="true">
      {WAVE.map((h, i) => <i key={i} style={{ height: `${h * 100}%`, animationDelay: `${(i % 6) * 90}ms` }} />)}
    </span>
  );
}

function HeroVisual() {
  const { booked } = useCallSim();
  return (
    <div className="dx-vis dx-in" style={{ animationDelay: '.25s' }}>
      <div className="dx-photo">
        <Image src="/images/clinic_hero_bg.jpg" alt="Clinic Reception" width={600} height={750} priority />
        <p className="dx-hello dx-deva dx-in" style={{ animationDelay: '1s' }}>नमस्ते</p>
        <div className="dx-call">
          <span className="dx-live" />
          <div>
            <p className="dx-call-t">Live Call Reception</p>
            <p className="dx-call-s">Caller: +91 98201 ••••</p>
          </div>
          <Wave live />
          <span className="dx-call-s">0:24</span>
        </div>
      </div>
      <div className="dx-slipwrap">
        <div className="dx-slip" data-booked={booked}>
          <div className="dx-slip-top">
            <p className="dx-slip-c">Metro Health Polyclinic</p>
            <p className="dx-slip-n dx-display">#08</p>
            <p className="dx-slip-w">{booked ? 'Dr. Mehta' : 'Open Slot'}</p>
            <p className="dx-slip-c">{booked ? 'Tomorrow, 10:15 AM' : '10:15 AM'}</p>
            <span className="dx-stamp" data-on={booked}>Locked In</span>
          </div>
          <div className="dx-slip-bot">
            <p className="dx-slip-w">{booked ? 'New Patient (Booked by AI)' : 'Available for booking'}</p>
            <p className="dx-slip-c">{booked ? 'Auto-synced via Live Telephony' : 'Empty'}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function ClinicDesk() {
  const { step, booked } = useCallSim();
  return (
    <div className="dx-desk">
      <div className="dx-desk-bar">
        <b>Dispatch AI · Metro Health Polyclinic</b>
        <span className="dx-chip dx-chip-sun"><span className="dx-live" /> OPD Active · 10:15 AM</span>
      </div>
      <div className="dx-kpis">
        {[['Patients in Queue', '14 Today'], ['Active Chamber', 'Token #04'], ['AI Calls Handled', '39 Calls'], ['Edge Voice Latency', '336ms']].map(([l, v]) => (
          <div key={l}><p>{l}</p><p className="dx-display">{v}</p></div>
        ))}
      </div>
      <div className="dx-desk-body">
        <div className="dx-chat">
          <div className="dx-chat-h">
            <div><b>Live Call Reception</b><p>Caller: +91 98201 ••••</p></div>
            <Wave live />
          </div>
          <div className="dx-chat-m">
            {MOCK_TRANSCRIPT.map((m, i) => (
              <div key={i} className={`dx-msg ${m.who === 'Patient' ? 'dx-msg-p' : 'dx-msg-a'}`}
                style={{ opacity: i <= step || booked ? 1 : 0, transform: i <= step || booked ? 'none' : 'translateY(8px)', fontWeight: i === step ? 600 : 400 }}>
                <small>{m.who === 'Patient' ? 'Patient' : 'AI'}</small>{m.text}
              </div>
            ))}
          </div>
          <p className="dx-chat-f"><span>Bilingual Speech Detection</span><b>Hindi + English Auto</b></p>
        </div>
        <div>
          <div className="dx-chat-h"><b>Chamber Queue · Dr. Mehta</b><p>Next Slot: 10:30 AM</p></div>
          {QUEUE.map((q) => (
            <div key={q.n} className="dx-q" data-active={!!q.active}>
              <span className="dx-q-n dx-display">{q.n}</span>
              <div><b>{q.name}</b><p>{q.note}</p></div>
              <span className={`dx-chip ${q.active ? 'dx-chip-sun' : ''}`}>{q.chip}</span>
            </div>
          ))}
          <div className="dx-q dx-slot" data-booked={booked}>
            <span className="dx-q-n dx-display">#08</span>
            <div><b>{booked ? 'New Patient (Booked by AI)' : 'Open Slot · 10:15 AM'}</b><p>{booked ? 'Auto-synced via Live Telephony' : 'Available for booking'}</p></div>
            <span className="dx-chip">{booked ? 'Locked In' : 'Empty'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Preview({ type }: { type: string }) {
  if (type === 'dashboard')
    return (
      <div className="dx-mini">
        <div className="dx-mini-h"><span>Token & Patient</span><span>Status & Chamber</span></div>
        <div className="dx-mini-r"><span className="dx-display">#01</span><b>Dr. Mehta Consultation</b><span className="dx-chip dx-chip-sun">In Chamber</span></div>
        <div className="dx-mini-r"><span className="dx-display">#02</span><b>Follow-up Review</b><span className="dx-chip">Next Up</span></div>
      </div>
    );
  if (type === 'voice')
    return (
      <div className="dx-mini">
        <div className="dx-mini-h"><span>Auto-Detect Dialect</span><span className="dx-chip dx-chip-sun">Streaming audio</span></div>
        <div className="dx-langs">
          {[['हिन्दी', 'Hindi', 1], ['Aa', 'English', 1], ['अ/Aa', 'Hinglish', 0], ['বাংলা', 'Bengali', 0], ['தமிழ்', 'Tamil', 0]].map(([g, n, on]) => (
            <span key={n as string} className="dx-lang" data-on={!!on}><b className={n === 'Hindi' ? 'dx-deva' : ''}>{g}</b>{n}</span>
          ))}
        </div>
      </div>
    );
  if (type === 'calendar')
    return (
      <div className="dx-mini">
        <div className="dx-mini-h"><span>Slot Duration: 15 mins</span><span>5 min Buffer Guard</span></div>
        <div className="dx-slots">
          {[['09:00', 'taken'], ['09:30', 'pick'], ['10:00', '']].map(([t, s]) => (
            <span key={t} className="dx-tslot" data-s={s}><b className="dx-display">{t}</b><i /></span>
          ))}
        </div>
      </div>
    );
  return (
    <div className="dx-mini">
      <div className="dx-mini-h"><span>Live Call Telemetry</span><span>Turn-by-turn audit</span></div>
      <div className="dx-bars">{[...WAVE, ...WAVE, ...WAVE].map((h, i) => <i key={i} style={{ height: `${h * 100}%` }} />)}</div>
      <p className="dx-mini-p">Every call session stores full transcript, audio recording, and triage classification</p>
    </div>
  );
}

function Frame({ src, alt, rev, dark, quote, cap, pos }: { src: string; alt: string; rev?: boolean; dark?: boolean; quote: string; cap: string; pos?: string }) {
  return (
    <div className="dx-fig">
      <div className={`dx-frame ${rev ? 'dx-frame-rev' : ''}`}>
        <Image src={src} alt={alt} fill sizes="(max-width: 1024px) 100vw, 42vw" style={{ objectFit: 'cover', objectPosition: pos || 'center' }} />
      </div>
      <div className={`dx-quote ${dark ? 'dx-quote-dark' : ''} ${rev ? 'dx-quote-rev' : ''}`}>
        <p className="dx-display">{quote}</p>
        <small>{cap}</small>
      </div>
    </div>
  );
}

const POINTS_VOICE = [
  { g: 'Voice', t: 'Streaming Voice Reception', b: 'LiveKit connects incoming audio to configured speech and language providers. Call telemetry records performance so latency can be measured in your deployment.' },
  { g: 'Speech', t: 'Configurable Speech Providers', b: 'Choose voice and speech settings supported by your configured providers. Language and accent support depend on the selected speech model.' },
  { g: '#08', t: 'Spoken Booking Confirmation', b: 'The receptionist reads back the proposed visit, waits for consent, and confirms only after the server saves the appointment.' },
];
const POINTS_QUEUE = [
  { g: '2→1', t: 'Dual-Stream Queue Balancing', b: 'Intelligently interleaves advance phone reservations with in-person walk-ins so consultation rooms run continuously without overcrowded lobbies.' },
  { g: 'DB', t: 'Transactional Capacity Checks', b: 'Booking rules and database locks check arrival-window capacity when phone and desk requests arrive concurrently.' },
  { g: '#04', t: 'Live Doctor Cockpit', b: 'Doctors view verified arrival order and AI-transcribed chief complaints before the patient even steps into the consultation chamber.' },
];

function Points({ items }: { items: typeof POINTS_VOICE }) {
  return (
    <div className="dx-points">
      {items.map((p) => (
        <div key={p.t} className="dx-point">
          <span className={`dx-glyph dx-display ${p.g === 'अ A' ? 'dx-deva' : ''}`}>{p.g}</span>
          <div><h3>{p.t}</h3><p>{p.b}</p></div>
        </div>
      ))}
    </div>
  );
}

export default function LandingPage() {
  const [menu, setMenu] = useState(false);
  const [active, setActive] = useState('');
  const stats = useInView<HTMLDivElement>(0.3);

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      let cur = '';
      for (const { id } of NAV) {
        const el = document.getElementById(id);
        if (el && y >= el.offsetTop - 180 && y < el.offsetTop - 180 + el.offsetHeight) { cur = id; break; }
      }
      setActive(cur);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return (
    <div className={`dx ${fDisplay.variable} ${fBody.variable} ${fDeva.variable}`}>
      <nav className="dx-nav">
        <div className="dx-wrap dx-nav-in">
          <Link href="/" className="dx-logo">
            <span className="dx-mark"><Image src={BRAND.logo} alt={BRAND.name} width={24} height={24} /></span>
            {BRAND.name}
          </Link>
          <div className="dx-links">
            {NAV.map((n) => <a key={n.id} href={`#${n.id}`} data-active={active === n.id}>{n.label}</a>)}
          </div>
          <div className="dx-nav-cta">
            <Link href="/login" prefetch className="dx-signin">Sign In</Link>
            <Link href="/signup" prefetch className="dx-btn dx-btn-ink dx-btn-sm">Get Started Free</Link>
          </div>
          <button type="button" className="dx-burger" onClick={() => setMenu(!menu)} aria-label="Toggle navigation">
            {menu ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
        {menu && (
          <div className="dx-wrap dx-mobile">
            {NAV.map((n) => <a key={n.id} href={`#${n.id}`} onClick={() => setMenu(false)}>{n.label}</a>)}
            <Link href="/login" prefetch onClick={() => setMenu(false)}>Sign In</Link>
            <Link href="/signup" prefetch onClick={() => setMenu(false)} className="dx-btn dx-btn-ink">Get Started Free</Link>
          </div>
        )}
      </nav>

      <header className="dx-hero">
        <div className="dx-wrap dx-hero-grid">
          <div>
            <h1 className="dx-display dx-h1 dx-in">
              Bring clinic calls and queues together.
              <br />
              Keep the front desk informed.
            </h1>
            <div className="dx-in" style={{ animationDelay: '.15s' }}>
              <p className="dx-lede">
                Dispatch AI connects configured clinic calls to a voice receptionist and brings appointments, walk-in queues, patient records, and billing into one dashboard.
              </p>
              <div className="dx-ctas">
                <Link href="/signup" prefetch className="dx-btn dx-btn-ink">Get Started Free</Link>
                <Link href="/login" prefetch className="dx-btn dx-btn-line">Sign In to Clinic</Link>
              </div>
              <p className="dx-note"><Check size={16} /> Autonomous Telephony & Dual-Stream OPD Engine</p>
            </div>
          </div>
          <HeroVisual />
        </div>
      </header>

      <section className="dx-stats dx-dark">
        <div ref={stats.ref} className="dx-wrap dx-stats-grid">
          {STATS.map((s) => (
            <div key={s.label} className="dx-tab">
              <p className="dx-display dx-stat-n">
                <em>{s.prefix}</em>
                {typeof s.value === 'number' ? <CountUp to={s.value} active={stats.seen} /> : s.value}
                <em>{s.suffix}</em>
              </p>
              <p className="dx-stat-l">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="features" className="dx-sec">
        <div className="dx-wrap">
          <h2 className="dx-display dx-h2">Complete practice automation without extra hardware</h2>
          <p className="dx-p" style={{ marginTop: 18 }}>
            Connect your regular clinic phone number and consultation calendar in minutes. Your staff needs zero training to use it.
          </p>
          <div style={{ marginTop: 48 }}><ClinicDesk /></div>
          <div className="dx-ledger">
            {FEATURES.map((f) => (
              <article key={f.title} className="dx-row">
                <p className="dx-rowtag">{f.tag}</p>
                <div><h3 className="dx-display">{f.title}</h3><p className="dx-p">{f.body}</p></div>
                <Preview type={f.type} />
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="voice-reception" className="dx-sec dx-wash">
        <div className="dx-wrap dx-split">
          <Frame src="/images/landing2.png" alt="Clinic receptionist warmly welcoming patient"
            quote="“Voice reception connected to the clinic schedule.”" cap="LiveKit Voice Reception" />
          <div>
            <p className="dx-tag">Natural voice telephony</p>
            <h2 className="dx-display dx-h2">The voice agent that sounds like your best front-desk receptionist</h2>
            <p className="dx-p" style={{ marginTop: 18 }}>
              Callers speak naturally without awkward robot pauses or keypad prompts. Dispatch AI handles FAQs, clinic directions, doctor specialties, and schedules tokens with human-grade warmth.
            </p>
            <Points items={POINTS_VOICE} />
          </div>
        </div>
      </section>

      <section id="chamber-queue" className="dx-sec">
        <div className="dx-wrap dx-split dx-split-rev">
          <div className="dx-order2">
            <p className="dx-tag">OPD clinical synchronization</p>
            <h2 className="dx-display dx-h2">A calm consultation room. A synchronized waiting lobby.</h2>
            <p className="dx-p" style={{ marginTop: 18 }}>
              Giving doctors complete focus on patient care while the queue organizes itself. Advance callers and physical walk-ins are balanced smoothly to eliminate lobby chaos.
            </p>
            <Points items={POINTS_QUEUE} />
          </div>
          <Frame src="/images/landing1.png" alt="Doctor listening attentively to patient during consultation" rev dark pos="center right"
            quote="“For the people in your care.”" cap="OPD Clinical Queue Synchronization" />
        </div>
      </section>

      <section id="how-it-works" className="dx-sec dx-wash">
        <div className="dx-wrap">
          <h2 className="dx-display dx-h2">From phone ring to confirmed consultation in seconds</h2>
          <p className="dx-p" style={{ marginTop: 18 }}>
            Dispatch AI acts as your dedicated front desk receptionist, ensuring no patient is left on hold or deflected to voicemail.
          </p>
          <div className="dx-steps">
            {STEPS.map((s, i) => (
              <div key={s.title} className="dx-step">
                <p className="dx-step-n dx-display">0{i + 1}</p>
                <h3 className="dx-display">{s.title}</h3>
                <p>{s.body}</p>
                <p className="dx-auto"><Check size={16} /> Automated End-to-End</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="dx-cta dx-dark">
        <svg className="dx-rings" viewBox="0 0 760 760" aria-hidden="true">
          {[0, 1.5, 3].map((d) => <circle key={d} className="dx-ring" cx="380" cy="380" r="370" fill="none" stroke="#F4B63A" strokeWidth="1.5" style={{ animationDelay: `${d}s` }} />)}
          <circle cx="380" cy="380" r="90" fill="none" stroke="#BFDDCD" strokeOpacity=".18" />
          <circle cx="380" cy="380" r="190" fill="none" stroke="#BFDDCD" strokeOpacity=".12" />
          <circle cx="380" cy="380" r="9" fill="#F4B63A" />
        </svg>
        <div className="dx-wrap" style={{ position: 'relative' }}>
          <p className="dx-tag dx-tag-d">Ready for your practice · Setup in 2 minutes</p>
          <h2 className="dx-display dx-cta-h">Stop losing patients to busy tones</h2>
          <p className="dx-cta-p">
            Create your clinic account today. Connect your phone number, configure doctor consultation hours, and let Dispatch AI answer every patient call with human-grade warmth.
          </p>
          <div className="dx-ctas">
            <Link href="/signup" prefetch className="dx-btn dx-btn-sun">Get Started Free</Link>
            <Link href="/login" prefetch className="dx-btn dx-btn-ghost">Sign In to Clinic</Link>
          </div>
        </div>
      </section>

      <footer className="dx-foot dx-dark">
        <div className="dx-wrap">
          <div className="dx-foot-grid">
            <div>
              <Link href="/" className="dx-logo"><span className="dx-mark"><Image src={BRAND.logo} alt={BRAND.name} width={24} height={24} /></span>{BRAND.name}</Link>
              <p className="dx-foot-p">Autonomous voice telephony and OPD queue intelligence for modern clinics and healthcare practices.</p>
              <p className="dx-chip dx-chip-sun" style={{ marginTop: 14 }}><span className="dx-live" /> Telephony Operational · 99.98% Uptime</p>
            </div>
            <div>
              <h4>Product</h4>
              <a href="#features">OPD Queue Cockpit</a>
              <a href="#voice-reception">Bilingual Voice Agent</a>
              <a href="#chamber-queue">Doctor Chamber Sync</a>
              <a href="#how-it-works">How It Works</a>
            </div>
            <div>
              <h4>Clinical Operations</h4>
              <span>Dual-Stream Quota Balancing</span>
              <span>Emergency Red-Flag Deflection</span>
              <span>Spoken Booking Confirmation</span>
              <span>Transactional Capacity Checks</span>
            </div>
            <div>
              <h4>Access & Platform</h4>
              <Link href="/signup">Get Started Free</Link>
              <Link href="/login">Doctor & Staff Sign In</Link>
              <span>Strict Data Privacy & Isolation</span>
              <span>E.164 Telephony Standard</span>
            </div>
          </div>
          <div className="dx-foot-end">
            <p>© 2026 Dispatch AI. All rights reserved. Built for modern clinical practices.</p>
            <p><Link href="/login">Sign In</Link> &nbsp; <Link href="/signup">Register Clinic</Link></p>
          </div>
        </div>
      </footer>
    </div>
  );
}