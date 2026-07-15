import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Everything except the marketing landing, auth pages and Next internals
// requires a signed-in user.
const isPublic = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api(.*)", // backend verifies the Bearer token itself
]);

export default clerkMiddleware(async (auth, req) => {
  if (!isPublic(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // skip Next internals and static files (incl. video/audio) unless in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpg|jpeg|png|gif|svg|ico|webp|woff2?|ttf|mp4|webm|mov|m4v|mp3|wav)).*)",
    "/(api|trpc)(.*)",
  ],
};
