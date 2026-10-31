import { setPlatformForTests } from "./index";
import { createWebPlatform } from "./web";

// The web adapter reads localStorage on every call, so tests that stub it keep working.
setPlatformForTests(createWebPlatform());
