# Pricing Service Guide

`ApiPricingService.ts` implements `IPricingService`; `index.ts` exports the typed `pricingService`. Pricing types live in `src/types/pricing`.

- GET `/payments/stripe/pricing` deliberately uses `skipAuth: true`; signed-out visitors can load pricing without bearer/account headers.
- POST `/payments/stripe/checkout` requires normal dashboard authentication/account context and returns `{ url }` for caller navigation. Do not copy the pricing read's anonymous option onto checkout.
- The retained `userEmail` argument is not backend identity. Preserve the actual checkout payload rather than using an email supplied by the browser to choose who is charged.
- Keep payment navigation/loading state and pricing CSS in consuming pages, not in the service.

No adjacent tests currently. Add anonymous pricing versus authenticated checkout boundary tests; from `spa/`, run `yarn test src/services/pricing` once added. See [services guide](../CONTRIBUTION.md).
