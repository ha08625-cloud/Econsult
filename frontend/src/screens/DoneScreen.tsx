import { PageShell } from "../layout";
import { useFocusHeading } from "../useFocusHeading";

interface DoneScreenProps {
  practiceName: string | null;
  practiceWasClosed: boolean;
}

export default function DoneScreen({ practiceName, practiceWasClosed }: DoneScreenProps) {
  const headingRef = useFocusHeading();
  return (
    <PageShell practiceName={practiceName}>
      <div className="done-icon" aria-hidden="true">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      
      <h1 ref={headingRef} tabIndex={-1}>Consultation submitted</h1>
      
      <p style={{ marginBottom: "var(--space-md)" }}>
        Your consultation has been submitted successfully.
      </p>
      
      {practiceWasClosed ? (
        <p className="screen-description">
          The practice is now closed — your submission will be reviewed on the
          next working day.
        </p>
      ) : (
        <p className="screen-description">
          If you do not hear back from the practice within the timeframe
          indicated, please contact them directly.
        </p>
      )}
    </PageShell>
  );
}