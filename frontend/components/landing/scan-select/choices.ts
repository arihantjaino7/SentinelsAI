/* The two scan engines, as data.

   Everything the chooser renders — copy, artwork, colour grading, where a
   click goes — lives in this one file. The components read it and render
   whatever they find; none of them know the word "GitHub".

   TO SWAP AN IMAGE: drop the new file in `frontend/public/` and change the
   `image` string. Nothing else moves.

   GIVE THE NEW FILE A NEW NAME — do not overwrite the old one in place.
   `next/image` serves these through `/_next/image?url=...`, and a browser
   that already has that exact URL will keep showing the OLD picture no
   matter how many times the file on disk changes or the dev server
   restarts. Changing the content means changing the URL. (Learned the hard
   way: the first swap kept the filenames and the page went on rendering the
   previous artwork through a full server restart and a forced reload.)

   THE COLOURS ARE MEASURED, NOT CHOSEN. Every hex below was sampled out of
   the reference recording frame by frame (hollywoodexhibit2026.com's gallery
   chooser), so this is a match rather than an impression:

     resting          #000000   flat black, no gradient anywhere
     left card hover  #252525   text #848080
     right card hover #E3E3E3   text #686868

   The pairing is the point: one dark mode, one light one. The two engines
   are supposed to feel like different rooms, and a page that goes from black
   to near-white says that before a single word is read. */

export type ScanChoiceId = "github" | "url";

/** A flat background + the text colour that sits on it. No gradients. */
export type Theme = {
  background: string;
  text: string;
};

/** Nothing hovered: pure black. */
export const RESTING_THEME: Theme = { background: "#000000", text: "#8B8884" };

export type ScanChoice = {
  id: ScanChoiceId;

  /** Which half of the pair this card sits in — decides which way it slides
      when it takes focus, and which side its headline unfurls toward. */
  side: "left" | "right";

  /* THE BIG TWO-LINE HEADLINE.

     Both lines are kept SHORT on purpose. At 6.2vw a long line runs off the
     screen, and the animation only reads as two lines converging if each one
     is a single word. The full name lives in `title`, on the card. */
  lineOne: string;
  lineTwo: string;

  /** The small caption under the card. */
  title: string;
  /** Second caption line — used for the not-yet-live engine. */
  note?: string;

  /** Path under `frontend/public/`. Swap this to change the artwork. */
  image: string;
  imageAlt: string;

  /** A click leaves for this route instead of revealing an input inline. */
  href?: string;

  theme: Theme;

  ariaLabel: string;
};

export const SCAN_CHOICES: ScanChoice[] = [
  {
    id: "github",
    side: "left",
    lineOne: "Scan",
    lineTwo: "GitHub",
    title: "GitHub Repository",
    image: "/card-github.jpg",
    imageAlt:
      "The GitHub mark on a dark rounded tile, circuit traces running out to either side",
    href: "/repo",
    theme: { background: "#252525", text: "#848080" },
    ariaLabel: "GitHub repository scanning",
  },
  {
    id: "url",
    side: "right",
    lineOne: "Scan",
    lineTwo: "Website",
    title: "Website URL",
    image: "/card-website.jpg",
    imageAlt:
      "A globe icon on a dark rounded tile, circuit traces running out to either side",
    theme: { background: "#E3E3E3", text: "#686868" },
    ariaLabel: "Website URL scanning",
  },
];
