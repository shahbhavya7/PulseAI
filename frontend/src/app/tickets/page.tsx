"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { getTickets } from "@/lib/api";
import type { TicketListResponse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { Card } from "@/components/Card";
import { LoadingCard, ErrorState, EmptyState } from "@/components/States";
import { TicketCard } from "@/components/TicketCard";
import { EMPTY_FILTERS, Filters, TicketFilters } from "@/components/TicketFilters";

export default function TicketsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);

  // Turn the UI filter state into the API's query params.
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
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Tickets</h1>
          <p className="mt-1 text-sm text-muted">
            Every ticket, grouped with the issues we found inside it.
          </p>
        </div>
        {state.data && (
          <span className="text-sm text-muted">
            {state.data.total} ticket{state.data.total === 1 ? "" : "s"}
          </span>
        )}
      </header>

      <TicketFilters value={filters} onChange={setFilters} />

      {state.loading && (
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <Card key={i}>
              <LoadingCard lines={3} />
            </Card>
          ))}
        </div>
      )}

      {state.error && <ErrorState error={state.error} onRetry={state.reload} />}

      {state.data && state.data.tickets.length === 0 && (
        <EmptyState
          icon={anyFilter ? "🔍" : "🎫"}
          title={anyFilter ? "No tickets match these filters" : "No tickets yet"}
        >
          {anyFilter ? (
            <p>Try widening or clearing the filters above.</p>
          ) : (
            <p>
              Head to the{" "}
              <Link href="/upload" className="text-accent hover:underline">
                Upload
              </Link>{" "}
              page to bring in some customer tickets.
            </p>
          )}
        </EmptyState>
      )}

      {state.data && state.data.tickets.length > 0 && (
        <div className="space-y-4">
          {state.data.tickets.map((ticket) => (
            <TicketCard key={ticket.id} ticket={ticket} onChanged={state.reload} />
          ))}
        </div>
      )}
    </div>
  );
}
