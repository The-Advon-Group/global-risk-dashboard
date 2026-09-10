"""Tests for reading France's 'Zones de vigilance' block.

The fixtures below mirror the structure of two real pages, checked by hand on
10 September 2026:

  * diplomatie.gouv.fr/fr/information-par-pays/seychelles/... - an h3 "Zones de
    vigilance" heading, then h4 band headings inside a separate div.fr-prose
    container, each followed by a <p> or <ul> describing the area. Seychelles is
    the case that exposed the bug: its red zone is the high seas north of the
    archipelago, for piracy, while the inhabited islands are green. Reading the
    whole page for band phrases published Seychelles as level 4.
  * .../nigeria/... - red and orange only, no green heading, and the red zone
    carries an exception clause naming a city.

Both pages repeat band phrases in the narrative below the block, which is why
the parser is scoped to the section and the tests include that trailing prose.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from collectors.france import _read_zones

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


SEYCHELLES = """
<article>
  <h2>Sécurité</h2>
  <div class="paragraph"><h3>Zones de vigilance</h3>
    <figure><figcaption>Dernière actualisation le 12/03/2026</figcaption></figure>
  </div>
  <div class="fr-prose">
    <h4>Zones formellement déconseillées</h4>
    <p>Zone de haute mer au nord de l’archipel seychellois, compte tenu du risque de piraterie.</p>
    <h4>Zones en vigilance renforcée</h4>
    <ul><li>Dans la zone maritime des Iles intérieures (Mahé, Praslin, La Digue,
      Silhouette et Frégate), la navigation de plaisance nécessite une vigilance renforcée.</li></ul>
    <h4>Zones en vigilance normale</h4>
    <p>Les Îles intérieures (Mahé, Praslin, La Digue et Silhouette) demeurent
      relativement sûres.</p>
  </div>
  <h3>Risques encourus et recommandations associées</h3>
  <div class="fr-prose">
    <h4>Piraterie maritime</h4>
    <p>La navigation au nord des Seychelles est formellement déconseillée, en
       raison de la menace de piraterie.</p>
  </div>
</article>
"""

NIGERIA = """
<article>
  <div class="paragraph"><h3>Zones de vigilance</h3></div>
  <div class="fr-prose">
    <h4>Zones formellement déconseillées (zone rouge)</h4>
    <p>Les déplacements sont formellement déconseillés :</p>
    <ul><li>dans le Nord-Est, les États de Borno, Yobe, Gombe, Bauchi, Adamawa,
       Jigawa et Kano, (à l’exception de la ville de Kano, déconseillée sauf
       raison impérative) ;</li></ul>
    <h4>Zones déconseillées sauf raisons impératives (zone orange)</h4>
    <p>Sont classés en zone orange :</p>
    <ul><li>dans la Middle Belt, les États de Benue, Nasarawa, Kogi, Plateau.</li></ul>
  </div>
  <h3>Risques encourus et recommandations associées</h3>
  <div class="fr-prose">
    <p>Certains déplacements sont déconseillés sauf raison impérative dans le reste du pays.</p>
  </div>
</article>
"""


def zones(html: str):
    return _read_zones(BeautifulSoup(html, "html.parser"))


def test_seychelles() -> None:
    print("Seychelles - the red zone is at sea and the islands are green")
    z = zones(SEYCHELLES)
    check("three bands read", len(z) == 3, str([(a, c[:30]) for a, _, c in z]))
    levels = [level for level, _, _ in z]
    check("highest first", levels == [4, 2, 1], str(levels))

    red = next(w for level, _, w in z if level == 4)
    check("the red zone keeps its own wording, not the band name",
          "haute mer" in red, red[:80])
    check("the band label is not the region text", "zone rouge" not in red.lower())

    green = next(w for level, _, w in z if level == 1)
    check("the green zone names the inhabited islands", "Mahé" in green, green[:80])


def test_narrative_is_not_scanned() -> None:
    print("Band phrases below the block are ignored")
    z = zones(NIGERIA)
    levels = sorted(level for level, _, _ in z)
    check("only the two bands France actually classified", levels == [3, 4], str(levels))
    joined = " ".join(w for _, _, w in z)
    check("the trailing narrative did not leak into a zone",
          "reste du pays" not in joined, joined[-90:])


def test_exception_clause_survives() -> None:
    print("Exception clauses reach the record")
    z = zones(NIGERIA)
    red = next(w for level, _, w in z if level == 4)
    check("the excepted city is present", "Kano" in red, red[:120])
    check("the exception wording is present", "exception" in red, red[:120])
    check("the states are present", "Borno" in red)


def test_heading_variants() -> None:
    print("Heading wordings vary between pages")
    with_colour = zones(NIGERIA)
    check("'(zone rouge)' suffix still matches red",
          any(level == 4 for level, _, _ in with_colour))
    check("'raisons impératives' plural still matches orange",
          any(level == 3 for level, _, _ in with_colour))


def test_no_block() -> None:
    print("A page with no zones block")
    check("returns nothing rather than guessing",
          zones("<article><h3>Sécurité</h3><p>rien</p></article>") == [])

    print("A band heading with no text under it")
    z = zones("""<article><h3>Zones de vigilance</h3><div class="fr-prose">
                 <h4>Zones en vigilance normale</h4></div></article>""")
    check("the band is still recorded", len(z) == 1 and z[0][0] == 1, str(z))
    check("with empty wording rather than the label", z[0][2] == "", repr(z[0][2]))


def test_same_band_twice() -> None:
    print("A colour split across two headings")
    html = """<article><h3>Zones de vigilance</h3><div class="fr-prose">
      <h4>Zones formellement déconseillées</h4><p>le Nord</p>
      <h4>Zones formellement déconseillées</h4><p>la zone frontalière</p>
      </div></article>"""
    z = zones(html)
    check("merged into one band", len(z) == 1, str(z))
    check("both areas kept", "Nord" in z[0][2] and "frontalière" in z[0][2], z[0][2])


if __name__ == "__main__":
    for fn in (test_seychelles, test_narrative_is_not_scanned,
               test_exception_clause_survives, test_heading_variants,
               test_no_block, test_same_band_twice):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
