import { PageShell } from "../layout";

interface DoneScreenProps {
  practiceWasClosed: boolean;
}

export default function DoneScreen({ practiceWasClosed }: DoneScreenProps) {
  return (
    <PageShell>
      <div className="done-icon">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <h1>Consultation submitted</h1>
      <p>Your consultation has been submitted successfully.</p>
      {practiceWasClosed ? (
        <p style={{ color: "var(--text-muted)" }}>
          The practice is now closed — your submission will be reviewed on the
          next working day.
        </p>
      ) : (
        <p style={{ color: "var(--text-muted)" }}>
          If you do not hear back from the practice within the timeframe
          indicated, please contact them directly.
        </p>
      )}
    </PageShell>
  );
}
