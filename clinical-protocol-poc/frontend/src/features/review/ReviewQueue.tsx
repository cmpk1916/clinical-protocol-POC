"use client";

import React from "react";
import { useEffect, useRef, useState } from "react";

import { protocolReviewApi, type ReviewApi } from "../../lib/api";
import type { ReviewItem, ReviewQueuePayload } from "../../lib/types";
import { EvidenceComparison } from "./EvidenceComparison";

type Props = {
  studyId: string;
  api?: ReviewApi;
};

type PendingApproval = {
  item: ReviewItem;
  confirmed: boolean;
};

export function ReviewQueue({ studyId, api = protocolReviewApi }: Readonly<Props>) {
  const [queue, setQueue] = useState<ReviewQueuePayload | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [busyFactId, setBusyFactId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflictRationales, setConflictRationales] = useState<Record<string, string>>({});
  const confirmationRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;

    api.getReviewQueue(studyId)
      .then((payload) => {
        if (active) setQueue(payload);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to load review queue");
      });

    return () => {
      active = false;
    };
  }, [api, studyId]);

  useEffect(() => {
    if (pendingApproval?.item.isCritical) {
      confirmationRef.current?.focus();
    }
  }, [pendingApproval]);

  if (error && !queue) {
    return <p role="alert">{error}</p>;
  }
  if (!queue) {
    return <p>Loading review queue…</p>;
  }

  const saveApproval = async (item: ReviewItem, explicitlyConfirmed: boolean) => {
    setBusyFactId(item.id);
    setError(null);
    try {
      const next = await api.approveFact({
        studyId,
        factId: item.id,
        versionToken: item.versionToken,
        explicitCriticalConfirmation: explicitlyConfirmed,
      });
      setQueue(next);
      setPendingApproval(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to approve fact");
    } finally {
      setBusyFactId(null);
    }
  };

  const approve = (item: ReviewItem) => {
    if (item.isCritical) {
      setPendingApproval({ item, confirmed: false });
      return;
    }

    void saveApproval(item, false);
  };

  const review = async (
    item: ReviewItem,
    action: "reject" | "defer" | "resume" | "resolve_conflict",
    rationale?: string,
  ) => {
    setBusyFactId(item.id);
    setError(null);
    try {
      setQueue(await api.reviewFact({
        studyId,
        factId: item.id,
        versionToken: item.versionToken,
        action,
        rationale: rationale ?? `${action === "reject" ? "Rejected" : action === "defer" ? "Deferred" : "Resumed"} during guided review.`,
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Unable to ${action} fact`);
    } finally {
      setBusyFactId(null);
    }
  };

  return (
    <section aria-labelledby="review-queue-heading">
      <h1 id="review-queue-heading">Guided Review</h1>
      {queue.readOnly ? (
        <p role="status">This archived review is read-only. Saved evidence remains available.</p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {queue.blockers.map((blocker) => (
        <p role="alert" key={blocker}>
          {blocker}
        </p>
      ))}
      <ol aria-label="Ordered review queue">
        {queue.items.map((item) => (
          <li key={item.id}>
            <article aria-labelledby={`${item.id}-heading`}>
              <h2 id={`${item.id}-heading`}>{item.label}</h2>
              <p>
                {item.category} · Status: {item.status} · Version token: {item.versionToken}
              </p>
              {item.evidenceValid === false ? (
                <p role="alert" aria-label="Exact evidence verification failed">
                  Exact source evidence could not be verified. Review actions are disabled.
                </p>
              ) : (
                <EvidenceComparison item={item} />
              )}
              <section aria-label={`Downstream impact for ${item.label}`}>
                <h3>Downstream impact</h3>
                <ul>
                  {item.downstreamImpact.map((impact) => (
                    <li key={impact}>{impact}</li>
                  ))}
                </ul>
              </section>
              <menu aria-label={`Review actions for ${item.label}`}>
                {item.status === "deferred" ? (
                  <button
                    type="button"
                    disabled={queue.readOnly || item.evidenceValid === false || busyFactId === item.id}
                    onClick={() => void review(item, "resume")}
                  >
                    Resume review
                  </button>
                ) : item.status === "conflict" ? (
                  <>
                    <label>
                      Conflict resolution rationale
                      <textarea
                        value={conflictRationales[item.id] ?? ""}
                        onChange={(event) => {
                          const rationale = event.currentTarget.value;
                          setConflictRationales((current) => ({
                            ...current,
                            [item.id]: rationale,
                          }));
                        }}
                      />
                    </label>
                    <button
                      type="button"
                      disabled={
                        queue.readOnly
                        || item.evidenceValid === false
                        || busyFactId === item.id
                        || !(conflictRationales[item.id] ?? "").trim()
                      }
                      onClick={() => void review(
                        item,
                        "resolve_conflict",
                        (conflictRationales[item.id] ?? "").trim(),
                      )}
                    >
                      Resolve conflict
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button" disabled={queue.readOnly || item.evidenceValid === false || busyFactId === item.id} onClick={() => approve(item)}>
                      Approve fact
                    </button>
                    <button type="button" disabled={queue.readOnly || item.evidenceValid === false || busyFactId === item.id} onClick={() => void review(item, "reject")}>Reject fact</button>
                    <button type="button" disabled={queue.readOnly || item.evidenceValid === false || busyFactId === item.id} onClick={() => void review(item, "defer")}>Defer fact</button>
                  </>
                )}
              </menu>
            </article>
          </li>
        ))}
      </ol>
      {queue.items.length === 0 ? <p role="status">All candidate facts have been reviewed.</p> : null}

      {pendingApproval ? (
        <form
          aria-label={`Critical approval for ${pendingApproval.item.label}`}
          onSubmit={(event) => {
            event.preventDefault();
            void saveApproval(pendingApproval.item, pendingApproval.confirmed);
          }}
        >
          <label>
            <input
              ref={confirmationRef}
              type="checkbox"
              required
              checked={pendingApproval.confirmed}
              onChange={(event) =>
                setPendingApproval({
                  item: pendingApproval.item,
                  confirmed: event.currentTarget.checked,
                })
              }
            />
            I explicitly confirm this critical fact
          </label>
          <p>Approval will use version token {pendingApproval.item.versionToken}.</p>
          <button type="submit" disabled={busyFactId === pendingApproval.item.id}>Confirm approval</button>
        </form>
      ) : null}
    </section>
  );
}
