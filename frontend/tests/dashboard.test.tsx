import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock Next.js navigation
const mockPush = vi.fn();
const mockParams = { id: "test-session-id-123" };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => mockParams,
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// Mock Supabase
const mockGetUser = vi.fn();
const mockGetSession = vi.fn();
const mockSignOut = vi.fn();

vi.mock("@/lib/supabase", () => ({
  createClient: () => ({
    auth: {
      getUser: mockGetUser,
      getSession: mockGetSession,
      signOut: mockSignOut,
    },
  }),
}));

// Mock fetch
global.fetch = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockGetUser.mockResolvedValue({
    data: { user: { email: "user@test.com" } },
  });
  mockGetSession.mockResolvedValue({
    data: { session: { access_token: "test-token" } },
  });
});

describe("DashboardPage", () => {
  it("shows usage meter", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => [],
    });

    const { default: DashboardPage } = await import("../app/dashboard/page");
    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByRole("progressbar")).toBeInTheDocument();
    });
  });

  it("shows upgrade button for free users", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => [],
    });

    const { default: DashboardPage } = await import("../app/dashboard/page");
    render(<DashboardPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /upgrade to pro/i }),
      ).toBeInTheDocument();
    });
  });
});

describe("ReportPage", () => {
  it("renders markdown headings", async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: "tok" } },
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({
        report_markdown: "## Executive Summary\n\nThis is the report body.",
        status: "completed",
      }),
    });

    const { default: ReportPage } = await import(
      "../app/dashboard/report/[id]/page"
    );
    render(<ReportPage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /executive summary/i })).toBeInTheDocument();
    });
  });

  it("citation links have target _blank", async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: "tok" } },
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({
        report_markdown:
          "## Summary\n\nSee [Source](https://example.com) for details.",
        status: "completed",
      }),
    });

    const { default: ReportPage } = await import(
      "../app/dashboard/report/[id]/page"
    );
    render(<ReportPage />);

    await waitFor(() => {
      const link = screen.getByRole("link", { name: "Source" });
      expect(link).toHaveAttribute("target", "_blank");
    });
  });

  it("download PDF button exists", async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: "tok" } },
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({
        report_markdown: "## Report\n\nContent.",
        status: "completed",
      }),
    });

    const { default: ReportPage } = await import(
      "../app/dashboard/report/[id]/page"
    );
    render(<ReportPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /download pdf/i }),
      ).toBeInTheDocument();
    });
  });
});
