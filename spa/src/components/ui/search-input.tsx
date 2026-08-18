import * as React from "react";
import { Search } from "lucide-react";

import { cn } from "../../lib/utils";
import { Input } from "./input";
import "./search-input.css";

const SearchInput = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, style, type = "search", ...props }, ref) => {
    return (
      <div className="search-input">
        <Search className="search-input__icon" aria-hidden="true" />
        <Input
          ref={ref}
          type={type}
          className={cn("search-input__control", className)}
          style={{ ...style, paddingInlineStart: "44px" }}
          {...props}
        />
      </div>
    );
  }
);
SearchInput.displayName = "SearchInput";

export { SearchInput };
