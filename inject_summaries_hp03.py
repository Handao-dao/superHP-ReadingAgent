"""Inject chapter summaries for hp03 (Prisoner of Azkaban)."""
import re
from pathlib import Path

CORPUS = Path(r"D:\d_Software\codeTrain\superhp_Agent\corpus\hp03")

SUMMARIES = {
    1: "Harry spends the summer doing homework while the Dursleys ignore him. On his birthday, he receives gifts from Ron, Hermione, and Hagrid, including a copy of the Daily Prophet revealing that Arthur Weasley won the annual Grand Prize Galleon Draw. The Weasley family uses the money to visit Egypt, and Ron sends Harry a magical Pocket Sneakoscope.",
    2: "The Dursleys host Aunt Marge, who insults Harry and his parents relentlessly. When she viciously slanders Harry's mother, Harry's magic erupts uncontrollably — he accidentally inflates Aunt Marge like a balloon. Furious and panicked, Harry runs away from Privet Drive with his trunk, determined never to return.",
    3: "Alone at night, Harry is startled by a large black dog and then rescued by the magical triple-decker Knight Bus. He travels to Diagon Alley, where Minister for Magic Cornelius Fudge personally greets him, astonishingly not punishing him for his magical outburst. Harry learns that Sirius Black, a dangerous murderer, has escaped from Azkaban prison and may be hunting him.",
    4: "Harry stays at the Leaky Cauldron for the remainder of the summer. He explores Diagon Alley, buys his school supplies, and encounters Ron and Hermione. At the pet shop, Hermione buys a ginger cat named Crookshanks. Harry overhears Arthur Weasley warn him that Sirius Black escaped Azkaban specifically to find Harry.",
    5: "On the Hogwarts Express, Harry, Ron, and Hermione share a compartment with a sleeping Professor Lupin. The train stops mid-journey and a terrifying Dementor enters, searching for Sirius Black. The Dementor's presence causes Harry to hear his mother's final screams and he faints. Lupin awakens and drives the creature away with a spell.",
    6: "Classes begin. Professor Trelawney, the eccentric Divination teacher, predicts Harry's death by reading tea leaves and identifies the Grim — a spectral death omen in the shape of a black dog. Hagrid's first Care of Magical Creatures lesson goes disastrously wrong when Draco Malfoy provokes Buckbeak the Hippogriff and gets injured.",
    7: "Professor Lupin teaches a memorable Defence Against the Dark Arts lesson where the class faces a Boggart. For Harry, the Boggart takes the form of a Dementor, revealing his deepest fear. Lupin privately explains that he prevented Harry from facing it, worrying it might have turned into Lord Voldemort.",
    8: "On Halloween, the Fat Lady's portrait is found slashed by Sirius Black, who tried to enter Gryffindor Tower. The entire school sleeps in the Great Hall while the castle is searched. During a Hogsmeade weekend, Harry stays behind and talks with Lupin, who offers to teach him how to fight Dementors.",
    9: "Gryffindor loses a Quidditch match to Hufflepuff when Harry is swarmed by Dementors and falls from his broom. His Nimbus Two Thousand is destroyed by the Whomping Willow. Afterwards, Harry resolves to learn the Patronus Charm from Lupin to defend himself against the Dementors.",
    10: "Fred and George give Harry the Marauder's Map, a magical map showing every person in Hogwarts and their location in real time. Using it, Harry sneaks into Hogsmeade through a secret passage. At the Three Broomsticks, he overhears Fudge, McGonagall, and Hagrid reveal the truth: Sirius Black was James Potter's best friend and betrayed the Potters to Voldemort.",
    11: "Harry receives a magnificent Firebolt racing broom as an anonymous Christmas gift. Hermione, suspicious that Sirius Black sent it, reports it to McGonagall, who confiscates it for safety checks. Harry and Ron are furious with Hermione, leading to a falling out between the three friends.",
    12: "Lupin teaches Harry the Patronus Charm in private lessons. Harry struggles but eventually produces a corporeal Patronus — a silver stag. Meanwhile, Ron finds Scabbers the rat bloodied, and evidence points to Crookshanks, deepening the rift between Hermione and the boys. The Firebolt is returned, declared safe.",
    13: "Gryffindor beats Ravenclaw in a crucial Quidditch match with Harry riding his Firebolt. After the game, Harry, exhausted, wakes to find Ron screaming — Sirius Black has slashed Ron's bed curtains with a knife while standing over him. The school goes into high alert, and Harry is moved into the Gryffindor common room for safety.",
    14: "Hagrid loses the case to protect Buckbeak, who is sentenced to execution. The trio visit Hagrid to console him, and Hermione discovers that Scabbers has vanished. On the way back to the castle, Ron is suddenly attacked by a large black dog and dragged into the Whomping Willow. Harry and Hermione follow him into the tunnel beneath.",
    15: "Gryffindor plays Slytherin in the Quidditch final. Despite Malfoy's dirty tactics and relentless taunting, Harry catches the Snitch to win the match and the Quidditch Cup for Gryffindor — their first victory in years. But Harry's triumph is overshadowed by the looming threat of Sirius Black and the events yet to unfold.",
    16: "During Harry's Divination exam, Professor Trelawney enters a trance and delivers a genuine prophecy: the Dark Lord's servant will return to him that night. That evening, the trio discover that Buckbeak's execution has been scheduled. They also learn that Sirius Black has been sighted on the grounds, and the castle is on lockdown.",
    17: "Harry, Ron, and Hermione go to Hagrid's hut where they find Scabbers alive. As they leave, Buckbeak's execution is carried out. Suddenly, the large black dog attacks Ron and drags him into the tunnel under the Whomping Willow. Harry and Hermione follow, leading them to the Shrieking Shack, where they confront Sirius Black.",
    18: "In the Shrieking Shack, Sirius Black reveals his true identity: he is innocent and was never the Potters' betrayer. Lupin arrives and explains the truth — Sirius, James, and Peter Pettigrew became Animagi to support Lupin when he became a werewolf. The real traitor is Peter Pettigrew, who faked his death and has been hiding as Ron's pet rat, Scabbers.",
    19: "Peter Pettigrew is forced back into human form. He confesses to betraying the Potters to Voldemort and framing Sirius. Lupin and Sirius prepare to kill Pettigrew, but Harry intervenes, insisting Pettigrew be handed over to the Dementors. On the way back, a full moon rises — Lupin transforms into a werewolf, and in the chaos Pettigrew escapes.",
    20: "Harry awakens in the hospital wing to learn that Sirius has been captured and the Dementors are about to perform the Dementor's Kiss on him. Dumbledore hints that Hermione should use her Time-Turner — a device she has been using all year to attend multiple classes. Harry and Hermione travel three hours back in time to save both Sirius and Buckbeak.",
    21: "Harry and Hermione, using the Time-Turner, secretly observe their past selves from earlier in the evening. They free Buckbeak and fly him to the tower where Sirius is imprisoned. As hundreds of Dementors descend upon Harry and Sirius by the lake, a powerful Patronus appears — Harry realizes the mysterious figure casting it was himself all along. He summons his own Patronus, a brilliant silver stag, to save them.",
    22: "Sirius escapes on Buckbeak and sends Harry a letter with permission for future Hogsmeade visits, along with a gift of a tiny owl (which Ron names Pigwidgeon). Dumbledore confirms that Pettigrew's escape means Voldemort will one day return and that Harry's mercy may prove significant. The term ends and Harry returns to the Dursleys, finally having something resembling a family in Sirius.",
}

def main():
    chapters = sorted(CORPUS.glob("hp03-ch*.md"))
    print(f"Injecting summaries into {len(chapters)} chapters...\n")
    for ch_path in chapters:
        m = re.match(r"hp03-ch(\d+)\.md", ch_path.name)
        if not m: continue
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
        if re.search(r"^summary:", parts[1], re.MULTILINE):
            print(f"  SKIP {ch_path.name}: already exists")
            continue
        new_fm = parts[1].rstrip() + f'\nsummary: "{summary}"'
        ch_path.write_text(f"---\n{new_fm}\n---{parts[2]}", encoding="utf-8")
        print(f"  OK {ch_path.name}")

if __name__ == "__main__":
    main()
