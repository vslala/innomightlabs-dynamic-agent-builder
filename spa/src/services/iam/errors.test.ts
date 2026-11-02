import { describe, expect, it } from "vitest";
import { HttpError } from "../http/client";
import { iamErrorCode, iamErrorMessage } from "./errors";

const refused = (code: string, message: string) => new HttpError(403, message, { code, message });

describe("IAM errors", () => {
  it("reads the code from the API's structured detail", () => {
    expect(iamErrorCode(refused("ESCALATION", "No"))).toBe("ESCALATION");
    expect(iamErrorCode(new HttpError(500, "Boom", "plain text"))).toBeUndefined();
    expect(iamErrorCode(new Error("Not HTTP"))).toBeUndefined();
  });

  it.each([
    ["ESCALATION", "You can only grant permissions you hold yourself", "account owner"],
    ["SEAT_LIMIT_REACHED", "The account has no available seats", "free a seat"],
    ["SEAT_LIMIT_UNAVAILABLE", "The account has no valid seat limit", "billing and seat availability"],
  ])("adds what to do next for %s", (code, message, next) => {
    const text = iamErrorMessage(refused(code, message));
    expect(text.startsWith(message)).toBe(true);
    expect(text).toContain(next);
  });

  it("keeps any other message as it is", () => {
    expect(iamErrorMessage(refused("NOT_FOUND", "There is no such member"))).toBe("There is no such member");
    expect(iamErrorMessage("not an error")).toBe("Please try again.");
  });
});
