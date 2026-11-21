import { useEffect, useMemo, useRef, useState } from 'react';
import './styles.css';
import { findQuoteSpan } from './quotes';

type Task = {
  id: string;
  name: string;
  owner: string | null;
  duration_days: number;
  depends_on: string[];
  quote: string;
};

type Finding = { title: string; detail: string; quote: string | null };

type Schedule = {
  status: 'scheduled' | 'cycle';
  schedule: { id: string; start_day: number; end_day: number }[];
  end_day: number | null;
  deadline_day: number | null;
  meets_deadline: boolean | null;
  days_late: number | null;
  cycle: string[];
};

type Plan = {
  id: string;
  text: string;
  review: { deadline_day: number | null; tasks: Task[]; findings: Finding[] };
  schedule: Schedule;
};

type PlanSummary = { id: string; title: string };

function VerdictBanner({ plan }: { plan: Plan }) {
  const { schedule, review } = plan;
  if (schedule.status === 'cycle') {
    const names = schedule.cycle.map(
      (id) => review.tasks.find((task) => task.id === id)?.name ?? id,
    );
    return (
      <div className="banner cycle">
        <div className="banner-title">Tasks wait on each other in a circle</div>
        <div className="banner-meta">{names.join(' → ')}</div>
      </div>
    );
  }
  const onTime = schedule.meets_deadline === true;
  return (
    <div className={`banner ${onTime ? 'on-time' : 'late'}`}>
      <div className="banner-top">
        <span className={`chip ${onTime ? '' : 'late'}`}>{onTime ? 'On time' : 'Late'}</span>
      </div>
      <div className="banner-title">
        {onTime ? 'The plan can finish by its date' : `${schedule.days_late} days late`}
      </div>
      <div className="banner-meta">
        {schedule.end_day === null ? (
          'No schedule'
        ) : (
          <>
            Ends day {schedule.end_day}
            {schedule.deadline_day === null ? '' : ` · deadline day ${schedule.deadline_day}`}
          </>
        )}
      </div>
    </div>
  );
}

function PlanDocument({ text, activeQuote }: { text: string; activeQuote: string | null }) {
  const span = useMemo(() => findQuoteSpan(text, activeQuote), [text, activeQuote]);
  const markRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (activeQuote !== null && span === null) {
      console.warn('Quote not found in plan:', activeQuote);
    }
  }, [activeQuote, span]);

  useEffect(() => {
    if (span) {
      markRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [span]);

  return (
    <div className="card proposal">
      <div className="plan-doc">
        {span ? (
          <>
            {text.slice(0, span.start)}
            <span className="quote-mark" ref={markRef}>
              {text.slice(span.start, span.end)}
            </span>
            {text.slice(span.end)}
          </>
        ) : (
          text
        )}
      </div>
    </div>
  );
}

function FindingsCard({
  findings,
  activeQuote,
  setActiveQuote,
}: {
  findings: Finding[];
  activeQuote: string | null;
  setActiveQuote: (quote: string | null) => void;
}) {
  if (findings.length === 0) {
    return (
      <div className="card">
        <div className="nothing">Nothing flagged</div>
      </div>
    );
  }
  return (
    <div className="card">
      {findings.map((finding, index) => {
        const hoverable = typeof finding.quote === 'string' && finding.quote.length > 0;
        return (
          <div
            key={index}
            className={`finding ${hoverable ? 'hoverable' : ''}`}
            onMouseEnter={hoverable ? () => setActiveQuote(finding.quote) : undefined}
            onMouseLeave={hoverable ? () => setActiveQuote(null) : undefined}
          >
            <p className="finding-title">{finding.title}</p>
            <p className="finding-detail">{finding.detail}</p>
            {!hoverable && <p className="finding-meta">No source line</p>}
          </div>
        );
      })}
    </div>
  );
}

function ScheduleCard({
  plan,
  activeQuote,
  setActiveQuote,
}: {
  plan: Plan;
  activeQuote: string | null;
  setActiveQuote: (quote: string | null) => void;
}) {
  const names = new Map(plan.review.tasks.map((task) => [task.id, task.name]));
  const quotes = new Map(plan.review.tasks.map((task) => [task.id, task.quote]));
  const rows = [...plan.schedule.schedule].sort(
    (a, b) => a.start_day - b.start_day || (names.get(a.id) ?? '').localeCompare(names.get(b.id) ?? ''),
  );
  const { schedule } = plan;
  const tail =
    schedule.status === 'cycle'
      ? 'No schedule'
      : schedule.end_day === null
        ? ''
        : `Ends day ${schedule.end_day}${
            schedule.deadline_day === null
              ? ''
              : ` · deadline day ${schedule.deadline_day}`
          }${
            schedule.meets_deadline === null
              ? ''
              : schedule.meets_deadline
                ? ' · on time'
                : ` · ${schedule.days_late} days late`
          }`;
  return (
    <div className="card">
      <table className="schedule-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Owner</th>
            <th className="num">Days</th>
            <th className="num">Start</th>
            <th className="num">End</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const quote = quotes.get(row.id) ?? null;
            return (
              <tr
                key={row.id}
                className={quote ? 'hoverable' : ''}
                onMouseEnter={quote ? () => setActiveQuote(quote) : undefined}
                onMouseLeave={quote ? () => setActiveQuote(null) : undefined}
              >
                <td>{names.get(row.id) ?? row.id}</td>
                <td>{plan.review.tasks.find((task) => task.id === row.id)?.owner ?? '—'}</td>
                <td className="num">{plan.review.tasks.find((task) => task.id === row.id)?.duration_days}</td>
                <td className="num">{row.start_day}</td>
                <td className="num">{row.end_day}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="schedule-meta">{tail}</div>
    </div>
  );
}

export default function App() {
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [plan, setPlan] = useState<Plan | null>(null);
  const [activeQuote, setActiveQuote] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/plans')
      .then((response) => response.json())
      .then((items: PlanSummary[]) => {
        setPlans(items);
        if (items.length > 0) setSelectedId(items[0].id);
      });
  }, []);

  useEffect(() => {
    setPlan(null);
    setActiveQuote(null);
    if (!selectedId) return;
    fetch(`/api/plans/${selectedId}`)
      .then((response) => response.json())
      .then(setPlan);
  }, [selectedId]);

  return (
    <div className="app">
      <div className="header">
        <h1 className="app-title">Plan review</h1>
        <div className="tabs">
          {plans.map((item) => (
            <button
              key={item.id}
              className={`tab ${item.id === selectedId ? 'active' : ''}`}
              onClick={() => setSelectedId(item.id)}
            >
              {item.title}
            </button>
          ))}
        </div>
      </div>
      {plan && (
        <>
          <VerdictBanner plan={plan} />
          <div className="grid">
            <div>
              <p className="section-label">Proposal</p>
              <PlanDocument text={plan.text} activeQuote={activeQuote} />
            </div>
            <div className="column-right">
              <div>
                <p className="section-label">Findings</p>
                <FindingsCard
                  findings={plan.review.findings}
                  activeQuote={activeQuote}
                  setActiveQuote={setActiveQuote}
                />
              </div>
              <div>
                <p className="section-label">Schedule</p>
                <ScheduleCard
                  plan={plan}
                  activeQuote={activeQuote}
                  setActiveQuote={setActiveQuote}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
