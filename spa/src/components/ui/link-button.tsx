import * as React from "react";
import { Link, type LinkProps } from "react-router-dom";
import { cn } from "../../lib/utils";
import { buttonVariants, type ButtonProps } from "./button";

type LinkButtonBaseProps = Omit<ButtonProps, "asChild" | "type"> & {
  children: React.ReactNode;
};

type InternalLinkButtonProps = LinkButtonBaseProps &
  Omit<LinkProps, "className" | "children"> & {
    href?: never;
    external?: false;
  };

type ExternalLinkButtonProps = LinkButtonBaseProps &
  Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "className" | "children"> & {
    href: string;
    to?: never;
    external: true;
  };

export type LinkButtonProps = InternalLinkButtonProps | ExternalLinkButtonProps;

export const LinkButton = React.forwardRef<HTMLAnchorElement, LinkButtonProps>(
  ({ className, variant, size, children, external, style, ...props }, ref) => {
    const classes = cn(buttonVariants({ variant, size, className }), "no-underline");

    if (external) {
      const { href, target = "_blank", rel, ...anchorProps } = props as ExternalLinkButtonProps;
      return (
        <a
          ref={ref}
          href={href}
          target={target}
          rel={rel ?? (target === "_blank" ? "noreferrer" : undefined)}
          className={classes}
          style={style}
          {...anchorProps}
        >
          {children}
        </a>
      );
    }

  const linkProps = props as InternalLinkButtonProps;
  return (
      <Link ref={ref} className={classes} style={style} {...linkProps}>
        {children}
      </Link>
    );
  }
);

LinkButton.displayName = "LinkButton";
