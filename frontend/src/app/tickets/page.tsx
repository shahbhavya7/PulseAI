"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, SearchX, Ticket } from "lucide-react";
import { getTickets } from "@/lib/api";
import type { TicketListResponse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { Card } from "@/components/Card";
import { LoadingCard, ErrorState, EmptyState } from "@/components/States";
import { TicketCard } from "@/components/TicketCard";
import { EMPTY_FILTERS, Filters, TicketFilters } from "@/components/TicketFilters";
import { PageTransition } from "@/components/motion";

export default function TicketsPage() {
  // useSearchParams needs a Suspense boundary for static prerender.
  return (
    <Suspense fallback={<TicketsSkeleton />}>
      <TicketsView />
    </Suspense>
  );
}

function TicketsSkeleton() {
  return (
    <div className="space-y-4">
      {[0, 1, 2].map((i) => (
        <Card key={i}>
          <LoadingCard lines={3} />
        </Card>
      ))}
    </div>
  );
}

function TicketsView() {
  const params = useSearchParams();
  // Seed the category filter from the URL (?category=bug) for click-to-filter
  // from the Overview charts.
  const [filters, setFilters] = useState<Filters>({
    ...EMPTY_FILTERS,
    category: params.get("category") ?? "",
  });

  const query = useMemo(
    () => ({
      category: filters.category || undefined,
      sentiment: filters.sentiment || undefined,
      minConfidence: filters.minConfidence ? Number(filters.minConfidence) : undefined,
      needsManualReview: filters.needsReview ? true : undefined,
      limit: 100,
    }),
    [filters],
  );

  const state = useAsync<TicketListResponse>(() => getTickets(query), [
    query.category,
    query.sentiment,
    query.minConfidence,
    query.needsManualReview,
  ]);

  const anyFilter =
    filters.category || filters.sentiment || filters.minConfidence || filters.needsReview;

  return (
    <PageTransition className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Tickets</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every ticket, grouped with the issues we found inside it.
          </p>
        </div>
        {state.data && (
          <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-sm text-muted-foreground">
            {state.data.total} ticket{state.data.total === 1 ? "" : "s"}
          </span>
        )}
      </header>

      <TicketFilters value={filters} onChange={setFilters} />

      {state.loading && <TicketsSkeleton />}

      {state.error && <ErrorState error={state.error} onRetry={state.reload} />}

      {state.data && state.data.tickets.length === 0 && (
        <EmptyState
          icon={anyFilter ? <SearchX /> : <Ticket />}
          title={anyFilter ? "No tickets match these filters" : "No tickets yet"}
        >
          {anyFilter ? (
            <p>Try widening or clearing the filters above.</p>
          ) : (
            <p className="inline-flex flex-wrap items-center justify-center gap-1">
              Head to the{" "}
              <Link
                href="/upload"
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                Upload <ArrowRight className="size-3.5" />
              </Link>{" "}
              page to bring in some customer tickets.
            </p>
          )}
        </EmptyState>
      )}

      {state.data && state.data.tickets.length > 0 && (
        <div className="space-y-4">
          {state.data.tickets.map((ticket, i) => (
            <TicketCard
              key={ticket.id}
              ticket={ticket}
              index={i}
              onChanged={state.reload}
            />
          ))}
        </div>
      )}
    </PageTransition>
  );
}
