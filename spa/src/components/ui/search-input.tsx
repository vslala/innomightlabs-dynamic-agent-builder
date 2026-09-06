import * as React from "react";
import { Search } from "lucide-react";

import { Input } from "./input";
import styles from "./search-input.module.css";

const SearchInput = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, style, type = "search", ...props }, ref) => {
    return (
      <div className={styles.searchInput}>
        <Search className={styles.searchInputIcon} aria-hidden="true" />
        <Input
          ref={ref}
          type={type}
          className={className}
          style={{ ...style, paddingInlineStart: "44px" }}
          {...props}
        />
      </div>
    );
  }
);
SearchInput.displayName = "SearchInput";

export { SearchInput };
