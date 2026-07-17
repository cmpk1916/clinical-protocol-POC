import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { GET } from "../../src/app/api/local/[...path]/route";
import { StudyDashboard } from "../../src/features/studies/StudyDashboard";
import type { StudySummary } from "../../src/lib/types";

afterEach(() => {
  cleanup();
  delete process.env.LOCAL_TENANT_ID;
  delete process.env.LOCAL_ACTOR_ID;
});

const archived: StudySummary = {
  id: "study-archived",
  name: "Archived Study",
  version: 2,
  lifecycle: "archived",
  updatedAt: "2026-07-16T10:00:00Z",
  archivedAt: "2026-07-16T10:00:00Z",
};

describe("StudyDashboard", () => {
  it("creates a study and moves archived studies between views", async () => {
    const requests: Array<{ url: string; body: unknown }> = [];
    const created = {
      id: "study-new",
      name: "Synthetic Alpha",
      version: 1,
      lifecycle: "active",
      updated_at: "2026-07-17T10:00:00Z",
      archived_at: null,
    };
    const activeItems = [created];
    const archivedItems = [
      {
        id: archived.id,
        name: archived.name,
        version: archived.version,
        lifecycle: archived.lifecycle,
        updated_at: archived.updatedAt,
        archived_at: archived.archivedAt,
      },
    ];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (init?.method === "POST") {
        return Response.json(created);
      }
      return Response.json({ items: url.includes("lifecycle=archived") ? archivedItems : activeItems });
    };

    try {
      render(<StudyDashboard initialActive={[]} initialArchived={[archived]} />);
      await userEvent.type(screen.getByLabelText("Study name"), "Synthetic Alpha");
      await userEvent.click(screen.getByRole("button", { name: "Create study" }));
      assert.ok(await screen.findByRole("link", { name: "Open Synthetic Alpha" }));
      assert.deepEqual(requests[0], {
        url: "/api/local/studies",
        body: { name: "Synthetic Alpha" },
      });

      await userEvent.click(screen.getByRole("tab", { name: "Archived" }));
      assert.ok(screen.getByText("Archived Study"));
      await userEvent.click(screen.getByRole("button", { name: "Restore Archived Study" }));
      assert.ok(
        requests.some(
          (request) =>
            request.url === "/api/local/studies/study-archived/restore" &&
            JSON.stringify(request.body) === JSON.stringify({ expected_version: 2 }),
        ),
      );

      await userEvent.click(screen.getByRole("tab", { name: "Active" }));
      const card = screen.getByText("Synthetic Alpha").closest("article");
      assert.ok(card);
      await userEvent.click(within(card).getByRole("button", { name: "Archive Synthetic Alpha" }));
      assert.ok(
        requests.some(
          (request) =>
            request.url === "/api/local/studies/study-new/archive" &&
            JSON.stringify(request.body) === JSON.stringify({ expected_version: 1 }),
        ),
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("explains the synthetic-only boundary when there are no studies", () => {
    render(<StudyDashboard initialActive={[]} initialArchived={[]} />);
    assert.match(
      screen.getByText(/This local proof of concept accepts synthetic data only/i).textContent ?? "",
      /synthetic/i,
    );
  });
});

describe("local API proxy", () => {
  it("rejects paths outside the allowlist without forwarding them", async () => {
    const originalFetch = globalThis.fetch;
    let forwarded = false;
    globalThis.fetch = async () => {
      forwarded = true;
      return new Response();
    };

    try {
      const response = await GET(new Request("http://localhost/api/local/admin/secrets"), {
        params: Promise.resolve({ path: ["admin", "secrets"] }),
      });
      assert.equal(response.status, 404);
      assert.equal(forwarded, false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("uses server identity and ignores browser identity headers", async () => {
    process.env.LOCAL_TENANT_ID = "server-tenant";
    process.env.LOCAL_ACTOR_ID = "server-actor";
    const originalFetch = globalThis.fetch;
    let forwardedHeaders: Headers | undefined;
    globalThis.fetch = async (_input, init) => {
      forwardedHeaders = new Headers(init?.headers);
      return Response.json({ items: [] });
    };

    try {
      const response = await GET(
        new Request("http://localhost/api/local/studies?lifecycle=active", {
          headers: {
            "X-Tenant-ID": "browser-tenant",
            "X-Actor-ID": "browser-actor",
            "X-Identity-Timestamp": "browser-timestamp",
            "X-Identity-Signature": "browser-signature",
          },
        }),
        { params: Promise.resolve({ path: ["studies"] }) },
      );
      assert.equal(response.status, 200);
      assert.equal(forwardedHeaders?.get("X-Tenant-ID"), "server-tenant");
      assert.equal(forwardedHeaders?.get("X-Actor-ID"), "server-actor");
      assert.equal(forwardedHeaders?.get("X-Identity-Timestamp"), null);
      assert.equal(forwardedHeaders?.get("X-Identity-Signature"), null);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
