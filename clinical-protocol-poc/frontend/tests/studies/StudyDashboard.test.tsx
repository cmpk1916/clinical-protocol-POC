import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import React from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import * as localRoute from "../../src/app/api/local/[...path]/route";
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

const active: StudySummary = {
  id: "study-active",
  name: "Active Study",
  version: 1,
  lifecycle: "active",
  updatedAt: "2026-07-17T10:00:00Z",
  archivedAt: null,
};

describe("StudyDashboard", () => {
  it("creates a study and moves archived studies between views", async () => {
    const requests: Array<{ url: string; body: unknown }> = [];
    type ApiStudy = {
      id: string;
      name: string;
      version: number;
      lifecycle: "active" | "archived";
      updated_at: string;
      archived_at: string | null;
    };
    const created: ApiStudy = {
      id: "study-new",
      name: "Synthetic Alpha",
      version: 1,
      lifecycle: "active",
      updated_at: "2026-07-17T10:00:00Z",
      archived_at: null,
    };
    let activeItems = [created];
    let archivedItems: ApiStudy[] = [
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
        if (url.endsWith("/restore")) {
          const restored = { ...archivedItems[0], version: 3, lifecycle: "active" as const, archived_at: null };
          archivedItems = archivedItems.filter((study) => study.id !== restored.id);
          activeItems = [...activeItems, restored];
          return Response.json(restored);
        }
        if (url.endsWith("/archive")) {
          const study = activeItems.find((item) => item.id === "study-new");
          assert.ok(study);
          const archivedStudy = {
            ...study,
            version: 2,
            lifecycle: "archived" as const,
            archived_at: "2026-07-17T11:00:00Z",
          };
          activeItems = activeItems.filter((item) => item.id !== archivedStudy.id);
          archivedItems = [...archivedItems, archivedStudy];
          return Response.json(archivedStudy);
        }
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
      await waitFor(() => assert.equal(screen.queryByText("Archived Study"), null));

      await userEvent.click(screen.getByRole("tab", { name: "Active" }));
      assert.ok(await screen.findByRole("link", { name: "Open Archived Study" }));
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
      await waitFor(() => assert.equal(screen.queryByText("Synthetic Alpha"), null));
      await userEvent.click(screen.getByRole("tab", { name: "Archived" }));
      assert.ok(await screen.findByText("Synthetic Alpha"));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("states every proof-of-concept limitation when studies are present", () => {
    render(<StudyDashboard initialActive={[active]} initialArchived={[archived]} />);
    const page = document.body.textContent ?? "";
    assert.match(page, /synthetic(?: data)? only/i);
    assert.match(page, /not validated/i);
    assert.match(page, /not for clinical use/i);
    assert.match(page, /not for regulatory use/i);
    assert.match(page, /not submission-ready/i);
  });

  it("states every proof-of-concept limitation when there are no studies", () => {
    render(<StudyDashboard initialActive={[]} initialArchived={[]} />);
    const page = document.body.textContent ?? "";
    assert.match(page, /synthetic(?: data)? only/i);
    assert.match(page, /not validated/i);
    assert.match(page, /not for clinical use/i);
    assert.match(page, /not for regulatory use/i);
    assert.match(page, /not submission-ready/i);
  });
});

describe("local API proxy", () => {
  it("does not expose a generic DELETE handler", () => {
    assert.equal("DELETE" in localRoute, false);
  });

  it("rejects paths outside the allowlist without forwarding them", async () => {
    const originalFetch = globalThis.fetch;
    let forwarded = false;
    globalThis.fetch = async () => {
      forwarded = true;
      return new Response();
    };

    try {
      const response = await localRoute.GET(new Request("http://localhost/api/local/admin/secrets"), {
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
      const response = await localRoute.GET(
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
