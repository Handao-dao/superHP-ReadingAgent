"""Inject pre-written chapter summaries for hp02 into frontmatter."""
import re
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[3] / "corpus" / "hp02"

SUMMARIES = {
    1: "Harry spends a miserable summer at the Dursleys, who are entertaining an important dinner guest. Dobby the house-elf appears in Harry's room, warning him not to return to Hogwarts, and when Harry refuses, Dobby causes chaos by destroying a dessert — resulting in Harry being locked in his room.",
    2: "Ron, Fred, and George rescue Harry from the Dursleys using their father's enchanted Ford Anglia. Harry learns that Dobby has been intercepting all his letters from friends. At the Burrow, Harry experiences the warm, chaotic, and loving atmosphere of the Weasley household for the first time.",
    3: "Harry enjoys life at the Burrow, helping de-gnome the garden. The Weasleys and Harry travel to Diagon Alley via Floo powder, but Harry mispronounces the destination and lands in Knockturn Alley, where he witnesses Lucius Malfoy selling suspicious items at Borgin and Burkes.",
    4: "Hagrid rescues Harry from Knockturn Alley. At Flourish and Blotts, the vain Gilderoy Lockhart, the new Defence Against the Dark Arts teacher, insists on a publicity photo with Harry. Harry meets Ginny Weasley and has a tense confrontation with Lucius Malfoy, who slips an old diary into Ginny's cauldron.",
    5: "When Harry and Ron are mysteriously blocked from Platform Nine and Three-Quarters, they fly the Ford Anglia to Hogwarts. They crash into the Whomping Willow, which destroys the car (sending it feral into the Forbidden Forest) and breaks Ron's wand. Snape threatens them with expulsion but they get off with detention.",
    6: "Life at Hogwarts resumes with Lockhart proving himself an incompetent narcissist. Harry serves detention answering Lockhart's fan mail. During one detention, Harry hears a mysterious, cold, murderous voice whispering in the walls — a voice that no one else can hear.",
    7: "During the first Quidditch practice, Draco Malfoy calls Hermione a 'Mudblood,' revealing deep wizard prejudice. Gryffindor beats Slytherin despite a rogue Bludger targeting Harry and breaking his arm. Lockhart's attempt to mend the break backfires spectacularly, removing all the bones from Harry's arm.",
    8: "Harry, Ron, and Hermione attend Nearly Headless Nick's 500th deathday party on Halloween. After leaving, Harry hears the sinister voice again and follows it to discover Mrs Norris, Filch's cat, hanging petrified with a bloody message on the wall: 'The Chamber of Secrets has been opened. Enemies of the heir, beware.'",
    9: "The school erupts in fear over the Chamber of Secrets. During History of Magic, Hermione asks Professor Binns about the legend, and they learn the Chamber was created by Salazar Slytherin to house a monster that would purge Muggle-borns from the school. Harry becomes a prime suspect.",
    10: "During a Quidditch match against Hufflepuff, a rogue Bludger relentlessly pursues Harry, breaking his arm again. Afterwards, Dobby admits to Harry that he enchanted the Bludger to force him to leave Hogwarts, and reveals that the Chamber of Secrets has been opened before — and that terrible things happened.",
    11: "Lockhart's disastrous Duelling Club reveals that Harry is a Parselmouth — he can speak to snakes. The entire school is horrified, as Parseltongue is associated with Salazar Slytherin and dark wizards. Everyone now suspects Harry is the Heir of Slytherin, leaving him isolated and feared.",
    12: "Hermione secretly brews Polyjuice Potion over the Christmas holidays. Harry and Ron transform into Crabbe and Goyle to infiltrate the Slytherin common room, where Draco reveals that the Chamber was opened fifty years ago and that a Muggle-born girl died. Hermione's potion backfires, leaving her half-cat.",
    13: "Harry discovers Tom Riddle's diary, which shows him a memory from fifty years ago: a young Hagrid is expelled for allegedly opening the Chamber, though Tom Riddle pins the blame on him. The diary is then stolen from Harry's dormitory, and Hermione is found petrified — but a clue in her hand reveals the monster is a Basilisk.",
    14: "The Minister for Magic arrives at Hogwarts to arrest Hagrid and take him to Azkaban. Dumbledore is suspended as Headmaster by the school governors, urged by Lucius Malfoy. Before Hagrid is taken away, he tells Harry and Ron to follow the spiders if they want answers.",
    15: "Harry and Ron follow the trail of spiders deep into the Forbidden Forest and meet Aragog, a giant spider raised by Hagrid. Aragog reveals he was not the monster from the Chamber and that the true creature is something spiders fear above all else. The boys narrowly escape being eaten.",
    16: "Harry realizes the entrance to the Chamber of Secrets is in Moaning Myrtle's bathroom. When Ginny Weasley is taken into the Chamber, Harry and Ron force Lockhart to help them. They discover the pipe entrance, but Lockhart tries to obliviate them — his spell backfires, causing a cave-in that separates Harry from the others.",
    17: "Harry descends into the Chamber of Secrets alone and finds Ginny's lifeless body next to Tom Riddle, who reveals himself as Lord Voldemort's younger self preserved in the diary. Riddle explains he possessed Ginny and unleashed the Basilisk. Harry must face both the monster and the memory of Voldemort.",
    18: "Fawkes the phoenix arrives bringing the Sorting Hat, then blinds the Basilisk. Harry pulls Godric Gryffindor's sword from the hat and slays the Basilisk, but is poisoned by its fang. Fawkes's tears heal him, and Harry destroys the diary with a Basilisk fang, saving Ginny. Dobby is freed from the Malfoys, and all petrified victims are restored.",
}

def main():
    chapters = sorted(CORPUS.glob("hp02-ch*.md"))
    print(f"Injecting summaries into {len(chapters)} chapters...\n")

    for ch_path in chapters:
        m = re.match(r"hp02-ch(\d+)\.md", ch_path.name)
        if not m:
            continue
        ch_no = int(m.group(1))
        summary = SUMMARIES.get(ch_no)
        if not summary:
            print(f"  SKIP {ch_path.name}: no summary")
            continue

        content = ch_path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) < 3:
            print(f"  SKIP {ch_path.name}: invalid frontmatter")
            continue

        frontmatter = parts[1].strip()
        body = parts[2]

        if re.search(r"^summary:", frontmatter, re.MULTILINE):
            print(f"  SKIP {ch_path.name}: already exists")
            continue

        new_frontmatter = frontmatter.rstrip() + f"\nsummary: \"{summary}\""
        ch_path.write_text(f"---\n{new_frontmatter}\n---{body}", encoding="utf-8")
        print(f"  OK {ch_path.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
