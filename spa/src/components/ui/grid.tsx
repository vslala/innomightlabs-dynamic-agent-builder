import * as React from "react";
import { cn } from "../../lib/utils";

type GridCols = 1 | 2 | 3 | 4 | 5 | 6 | 12;

interface GridProps extends React.HTMLAttributes<HTMLDivElement> {
  cols?: GridCols;
  colsSm?: GridCols;
  colsMd?: GridCols;
  colsLg?: GridCols;
  colsXl?: GridCols;
  gap?: "none" | "sm" | "md" | "lg" | "xl";
  children: React.ReactNode;
}

const colsMap: Record<GridCols, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
  5: "grid-cols-5",
  6: "grid-cols-6",
  12: "grid-cols-12",
};

const colsSmMap: Record<GridCols, string> = {
  1: "sm:grid-cols-1",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-4",
  5: "sm:grid-cols-5",
  6: "sm:grid-cols-6",
  12: "sm:grid-cols-12",
};

const colsMdMap: Record<GridCols, string> = {
  1: "md:grid-cols-1",
  2: "md:grid-cols-2",
  3: "md:grid-cols-3",
  4: "md:grid-cols-4",
  5: "md:grid-cols-5",
  6: "md:grid-cols-6",
  12: "md:grid-cols-12",
};

const colsLgMap: Record<GridCols, string> = {
  1: "lg:grid-cols-1",
  2: "lg:grid-cols-2",
  3: "lg:grid-cols-3",
  4: "lg:grid-cols-4",
  5: "lg:grid-cols-5",
  6: "lg:grid-cols-6",
  12: "lg:grid-cols-12",
};

const colsXlMap: Record<GridCols, string> = {
  1: "xl:grid-cols-1",
  2: "xl:grid-cols-2",
  3: "xl:grid-cols-3",
  4: "xl:grid-cols-4",
  5: "xl:grid-cols-5",
  6: "xl:grid-cols-6",
  12: "xl:grid-cols-12",
};

const gapMap: Record<string, string> = {
  none: "gap-0",
  sm: "gap-4",
  md: "gap-6",
  lg: "gap-8",
  xl: "gap-10",
};

export const Grid = React.forwardRef<HTMLDivElement, GridProps>(
  (
    {
      className,
      cols = 1,
      colsSm,
      colsMd,
      colsLg,
      colsXl,
      gap = "md",
      children,
      ...props
    },
    ref
  ) => {
    return (
      <div
        ref={ref}
        className={cn(
          "grid",
          colsMap[cols],
          colsSm && colsSmMap[colsSm],
          colsMd && colsMdMap[colsMd],
          colsLg && colsLgMap[colsLg],
          colsXl && colsXlMap[colsXl],
          gapMap[gap],
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Grid.displayName = "Grid";

interface StackProps extends React.HTMLAttributes<HTMLDivElement> {
  gap?: "none" | "xs" | "sm" | "md" | "lg" | "xl";
  children: React.ReactNode;
}

const stackGapMap: Record<string, string> = {
  none: "space-y-0",
  xs: "space-y-2",
  sm: "space-y-4",
  md: "space-y-6",
  lg: "space-y-8",
  xl: "space-y-10",
};

export const Stack = React.forwardRef<HTMLDivElement, StackProps>(
  ({ className, gap = "md", children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(stackGapMap[gap], className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Stack.displayName = "Stack";

interface CenterProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const Center = React.forwardRef<HTMLDivElement, CenterProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn("flex flex-col items-center justify-center", className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Center.displayName = "Center";
