import type { Message } from "../../types/message";

export type FormSubmissionAnswer = {
  label: string;
  value: string;
};

export type FormSubmission = {
  label: string;
  answers: FormSubmissionAnswer[];
};

function decodeValue(value: string): string {
  return value.replace(/\\n/g, "\n");
}

export function parseFormSubmission(content: string): FormSubmission | null {
  const labelMatch = content.match(/^<form_submission label="([^"]+)">/);
  const bodyMatch = content.match(/^<form_submission label="[^"]+">\n([\s\S]*?)\n<\/form_submission>/);
  if (!labelMatch || !bodyMatch) {
    return null;
  }

  const answers = bodyMatch[1]
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => {
      const text = line.slice(2);
      const separator = text.indexOf(": ");
      if (separator === -1) {
        return { label: "Answer", value: decodeValue(text) };
      }
      return {
        label: text.slice(0, separator),
        value: decodeValue(text.slice(separator + 2)),
      };
    });

  return {
    label: labelMatch[1],
    answers,
  };
}

export function isSubmittedFormMessage(message: Message): boolean {
  return parseFormSubmission(message.content) !== null;
}
