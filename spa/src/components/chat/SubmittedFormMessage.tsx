import type { Message } from "../../types/message";
import styles from "./SubmittedFormMessage.module.css";
import { parseFormSubmission } from "./submittedFormParser";

function AnswerValue({ value }: { value: string }) {
  return <div className={styles.value}>{value || "No answer"}</div>;
}

export function SubmittedFormMessage({ message }: { message: Message }) {
  const submission = parseFormSubmission(message.content);
  if (!submission) {
    return null;
  }

  return (
    <div className={styles.form}>
      <div className={styles.header}>
        <div className={styles.title}>{submission.label}</div>
        <div className={styles.eyebrow}>Submitted form</div>
      </div>
      {submission.answers.length > 0 && (
        <div className={styles.answers}>
          {submission.answers.map((answer, index) => (
            <div key={`${answer.label}-${index}`} className={styles.field}>
              <div className={styles.label}>{answer.label}</div>
              <AnswerValue value={answer.value} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
