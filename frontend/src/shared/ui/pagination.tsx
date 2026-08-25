"use client";

import { useTranslations } from "next-intl";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { Button } from "./button";

export interface PaginationProps {
  page: number; // 1-indexed
  pageSize: number;
  total: number;
  onPageChange: (newPage: number) => void;
  onPageSizeChange?: (newPageSize: number) => void;
  pageSizeOptions?: number[];
  className?: string;
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 25, 50, 100],
  className = "",
}: PaginationProps) {
  const t = useTranslations("common.pagination");

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(Math.max(1, page), totalPages);

  const from = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const to = Math.min(currentPage * pageSize, total);

  // Generate page numbers with window
  const getPageNumbers = () => {
    const pages: (number | "ellipsis")[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      pages.push(1);
      if (currentPage > 3) {
        pages.push("ellipsis");
      }

      const start = Math.max(2, currentPage - 1);
      const end = Math.min(totalPages - 1, currentPage + 1);

      for (let i = start; i <= end; i++) {
        pages.push(i);
      }

      if (currentPage < totalPages - 2) {
        pages.push("ellipsis");
      }
      pages.push(totalPages);
    }
    return pages;
  };

  return (
    <div
      className={`flex flex-col gap-4 px-6 py-4 sm:flex-row sm:items-center sm:justify-between border-t border-border/40 bg-card/40 backdrop-blur-md ${className}`}
    >
      {/* Left: Range and total */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>
          {t("showing")}{" "}
          <strong className="font-mono font-bold text-foreground">{from}</strong> -{" "}
          <strong className="font-mono font-bold text-foreground">{to}</strong>{" "}
          {t("of")}{" "}
          <strong className="font-mono font-bold text-foreground">{total}</strong>{" "}
          {t("results")}
        </span>

        {onPageSizeChange && (
          <div className="flex items-center gap-1.5 ml-2 border-l border-border/50 pl-3">
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="h-7 rounded-lg border border-border/60 bg-background/80 px-2 font-mono text-xs font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-2xs"
            >
              {pageSizeOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt} {t("perPage")}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Right: Page controls */}
      <div className="flex items-center gap-1 self-end sm:self-auto">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(1)}
          disabled={currentPage <= 1}
          className="size-8 p-0 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
          title={t("prev")}
        >
          <ChevronsLeft className="size-4" />
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          className="size-8 p-0 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
          title={t("prev")}
        >
          <ChevronLeft className="size-4" />
        </Button>

        <div className="flex items-center gap-1 px-1">
          {getPageNumbers().map((p, idx) =>
            p === "ellipsis" ? (
              <span
                key={`ellipsis-${idx}`}
                className="flex size-8 items-center justify-center text-xs text-muted-foreground font-mono"
              >
                ...
              </span>
            ) : (
              <Button
                key={p}
                variant={p === currentPage ? "default" : "ghost"}
                size="sm"
                onClick={() => onPageChange(p)}
                className={`size-8 p-0 text-xs font-mono font-bold cursor-pointer ${
                  p === currentPage
                    ? "bg-primary text-primary-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                {p}
              </Button>
            ),
          )}
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="size-8 p-0 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
          title={t("next")}
        >
          <ChevronRight className="size-4" />
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage >= totalPages}
          className="size-8 p-0 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
          title={t("next")}
        >
          <ChevronsRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
