"""Inject pre-written chapter summaries into frontmatter."""
import re
from pathlib import Path

CORPUS = Path(r"D:\d_Software\codeTrain\superhp_Agent\corpus\hp01")

SUMMARIES = {
    1: "The Dursleys, a perfectly normal family, witness strange occurrences as the wizarding world celebrates Voldemort's downfall. Dumbledore, McGonagall, and Hagrid leave the infant Harry Potter on the Dursleys' doorstep with a letter explaining his parents' murder and his survival of the Killing Curse.",
    2: "Ten years later, Harry lives miserably with the Dursleys, sleeping in a cupboard under the stairs. During a trip to the zoo for Dudley's birthday, Harry accidentally makes the glass of a boa constrictor's enclosure vanish, freeing the snake and trapping Dudley inside — the first sign of his magical abilities.",
    3: "Mysterious letters addressed to Harry begin arriving at Privet Drive, growing in number despite Uncle Vernon's escalating attempts to stop them. The family flees to a remote hut on a rock in the sea, but Hagrid finds them on Harry's eleventh birthday, delivering the letter in person.",
    4: "Hagrid bursts into the hut, reveals that Harry is a wizard, and tells him the truth about his parents' murder by Lord Voldemort. He takes Harry away from the Dursleys to begin his new life, revealing Harry's fame in the wizarding world as the Boy Who Lived.",
    5: "Hagrid takes Harry to Diagon Alley, the hidden wizarding shopping district, where Harry discovers his fame and visits Gringotts bank. Hagrid retrieves a mysterious small package from vault 713. Harry buys his school supplies, meets a nervous boy named Draco Malfoy, and obtains a wand that shares a core with Voldemort's.",
    6: "Harry navigates King's Cross Station to find Platform Nine and Three-Quarters, where he meets the warm Weasley family. On the Hogwarts Express, he befriends Ron Weasley and meets bossy Hermione Granger, while his rivalry with Draco Malfoy begins. He also shares his first sweets and stories with Ron.",
    7: "The first-years cross the lake to Hogwarts Castle and are sorted into houses by the Sorting Hat. Harry, Ron, and Hermione all join Gryffindor. During the welcoming feast, Harry notices Professor Snape staring at him, and his lightning-bolt scar gives a painful twinge.",
    8: "Classes begin and Professor Snape publicly humiliates Harry in his first Potions lesson, revealing a deep-seated hostility. Harry learns more about the forbidden third-floor corridor that Dumbledore declared off-limits, and begins to suspect something mysterious is being guarded there.",
    9: "Malfoy challenges Harry to a midnight duel, but it turns out to be a trap to get him caught out of bed. While fleeing from Filch, Harry, Ron, and Hermione accidentally stumble into the forbidden third-floor corridor and encounter a giant three-headed dog standing guard over a trapdoor.",
    10: "During the Halloween feast, a mountain troll is let into the castle. Harry and Ron rescue Hermione, who is trapped in the girls' bathroom with the troll. The three become inseparable friends. Afterwards, Harry notices Snape limping with a bloody, bitten leg heading toward the third floor.",
    11: "Harry plays his first Quidditch match as Gryffindor's youngest Seeker in a century. His broom tries to throw him off — Hermione spots Snape muttering a jinx and sets his robes on fire to break his concentration. Harry catches the Golden Snitch in his mouth, winning the match for Gryffindor.",
    12: "While exploring the castle under his Invisibility Cloak on Christmas night, Harry discovers the Mirror of Erised, which shows him his deepest desire — his lost parents standing beside him. Dumbledore finds Harry and gently warns him that the mirror will be moved, advising him not to dwell on dreams and forget to live.",
    13: "Harry, Ron, and Hermione learn that the three-headed dog is guarding the Philosopher's Stone, a legendary object created by Nicolas Flamel that grants immortality. They deduce that Snape is trying to steal it for Voldemort, and Harry begins secretly researching the Stone while also serving as Seeker for Gryffindor's next Quidditch match.",
    14: "Hagrid wins a dragon egg in a card game and hatches a Norwegian Ridgeback named Norbert. As the dragon grows dangerously large, Harry, Ron, and Hermione arrange a secret midnight handover to send Norbert to Romania. They succeed, but are caught sneaking back and lose Gryffindor a devastating 150 house points.",
    15: "Harry, Hermione, Neville, and Malfoy serve their detention in the Forbidden Forest with Hagrid, searching for an injured unicorn. Harry encounters a hooded figure drinking the unicorn's blood and is rescued by Firenze, a centaur, who explains that drinking unicorn blood gives a cursed half-life — strongly implying that Voldemort is hunting the Stone.",
    16: "Determined to stop the theft, Harry, Ron, and Hermione go through the trapdoor. They overcome a series of protective enchantments: Devil's Snare, flying keys, a life-sized wizard chess game in which Ron sacrifices himself, and a logic puzzle solved by Hermione. Harry proceeds alone to face whoever waits beyond.",
    17: "Harry discovers that Quirrell, not Snape, is the true villain — Voldemort's face is on the back of Quirrell's head. Harry retrieves the Philosopher's Stone from the Mirror of Erised through his pure intentions. His touch burns Quirrell due to the protection of his mother's love. Dumbledore explains that the Stone has been destroyed, and Gryffindor wins the House Cup at the end-of-year feast.",
}

def inject_summary(filepath, summary_text):
    content = filepath.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        print(f"  SKIP {filepath.name}: invalid frontmatter")
        return False

    frontmatter = parts[1].strip()
    body = parts[2]

    if re.search(r"^summary:", frontmatter, re.MULTILINE):
        print(f"  SKIP {filepath.name}: summary already exists")
        return True

    new_frontmatter = frontmatter.rstrip() + f"\nsummary: \"{summary_text}\""
    new_content = f"---\n{new_frontmatter}\n---{body}"
    filepath.write_text(new_content, encoding="utf-8")
    return True


def main():
    chapters = sorted(CORPUS.glob("hp01-ch*.md"))
    print(f"Injecting summaries into {len(chapters)} chapters...\n")

    for ch_path in chapters:
        # Extract chapter number from filename
        m = re.match(r"hp01-ch(\d+)\.md", ch_path.name)
        if not m:
            continue
        ch_no = int(m.group(1))
        summary = SUMMARIES.get(ch_no)
        if not summary:
            print(f"  SKIP {ch_path.name}: no summary for chapter {ch_no}")
            continue

        ok = inject_summary(ch_path, summary)
        if ok:
            print(f"  OK {ch_path.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
