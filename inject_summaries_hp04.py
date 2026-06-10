"""Inject chapter summaries for hp04 (Goblet of Fire)."""
import re
from pathlib import Path

CORPUS = Path(r"D:\d_Software\codeTrain\superhp_Agent\corpus\hp04")

SUMMARIES = {
    1: "In the village of Little Hangleton, the Riddle House caretaker Frank Bryce overhears Wormtail and Lord Voldemort plotting in the old Riddle manor. Voldemort discusses a plan involving Harry Potter and kills Frank when he is discovered.",
    2: "Harry wakes from a vivid nightmare in which Voldemort murdered someone. His scar hurts for the first time in years. He writes to Sirius Black about his scar and prepares to join the Weasleys for the Quidditch World Cup.",
    3: "Uncle Vernon receives a letter from Mrs Weasley inviting Harry to the Quidditch World Cup. After tense negotiations, the Dursleys reluctantly agree for the Weasleys to collect Harry. The Weasley twins, Ron, and Mr Weasley arrive via Floo powder, accidentally destroying half the Dursleys' living room.",
    4: "Harry returns to the Burrow. Life with the Weasleys is chaotic and joyful. The family, along with Harry and Hermione, prepare to travel to the Quidditch World Cup via Portkey, departing at dawn.",
    5: "Fred and George experiment with their joke products, testing them on younger students and preparing to launch Weasleys' Wizard Wheezes. Their entrepreneurial ambition and inventiveness are on full display as they dream of opening a joke shop.",
    6: "The group travels by Portkey to the Quidditch World Cup campsite. They encounter wizards from around the world, meeting Cedric Diggory and his father, and Ludo Bagman. The atmosphere is festive with magical tents and international camaraderie.",
    7: "At the top box of the stadium, Harry meets Winky, Barty Crouch's house-elf. The match begins — Ireland versus Bulgaria — featuring Viktor Krum, the world's best Seeker. Ireland wins the match, but Krum catches the Snitch, ending the game on Bulgaria's terms despite their heavy defeat.",
    8: "After the Cup, the campsite erupts in chaos as masked Death Eaters march through, tormenting Muggles and setting fires. In the confusion, someone conjures the Dark Mark into the sky, causing mass panic. Harry, Ron, and Hermione flee into the woods and encounter Draco Malfoy.",
    9: "Barty Crouch Sr furiously investigates the Dark Mark conjuring and discovers Winky, his house-elf, holding Harry's wand nearby. Despite evidence suggesting Winky didn't cast the Mark, Crouch coldly dismisses her from service. Mr Weasley and the Ministry try to cover up the incident.",
    10: "Back at the Burrow, the Daily Prophet reports on the Dark Mark incident. The Weasleys take Harry, Ron, and Hermione to Diagon Alley, where they witness arguments at the Ministry about security. The group gets their school supplies and learn that something exciting is planned at Hogwarts this year.",
    11: "On the Hogwarts Express, Harry learns about the Triwizard Tournament from Ron and Hermione. He also meets the new Defence Against the Dark Arts teacher, the grizzled ex-Auror Alastor 'Mad-Eye' Moody, under dramatic circumstances involving Draco Malfoy being turned into a ferret.",
    12: "At the start-of-term feast, Dumbledore announces the Triwizard Tournament — a legendary competition between Hogwarts, Beauxbatons, and Durmstrang. Students under seventeen are barred from entering. The Goblet of Fire will choose one champion from each school. The announcement electrifies the entire school.",
    13: "Moody teaches his first lesson by demonstrating the three Unforgivable Curses on spiders, shocking the class. Harry is particularly disturbed by the Killing Curse. Herbology and other classes continue, with tensions building as the students await the arrival of the visiting schools.",
    14: "The Beauxbatons and Durmstrang delegations arrive spectacularly — Beauxbatons in a giant flying carriage and Durmstrang emerging from a ship that rises from the Black Lake. Viktor Krum is revealed to be a Durmstrang student. The Goblet of Fire is placed in the Entrance Hall.",
    15: "On Halloween, the Goblet of Fire selects the champions: Viktor Krum for Durmstrang, Fleur Delacour for Beauxbatons, and Cedric Diggory for Hogwarts. But then, impossibly, a fourth name emerges — Harry Potter. Harry is thrust into the tournament against his will, and the school is divided over whether he cheated.",
    16: "The four champions gather for the Weighing of the Wands ceremony, conducted by Mr Ollivander and witnessed by Rita Skeeter. Harry gives an interview to Skeeter that is later published with bizarre fabrications. Ron's jealousy over Harry being a champion creates a deep rift between them.",
    17: "The champions learn that the first task involves facing a dragon. Harry, warned by Hagrid and Mad-Eye Moody, realizes he must get past a Hungarian Horntail. Hermione helps him prepare by practicing the Summoning Charm relentlessly. Harry decides his strategy — he will summon his Firebolt and outfly the dragon.",
    18: "With Ron finally believing Harry didn't enter himself, the two reconcile. Ron's immense relief is palpable as he realizes Harry is in genuine danger. The day before the first task arrives, and Harry prepares his Summoning Charm for the challenge ahead.",
    19: "Harry faces the Hungarian Horntail in the first task. Using his Summoning Charm, he calls his Firebolt and flies rings around the dragon, retrieving the golden egg by outmaneuvering the furious beast. The crowd goes wild, and Harry earns high marks, tying with Krum for first place.",
    20: "The champions are told the golden eggs contain a clue for the second task. When Harry opens his, it emits a horrible screeching. Hagrid reveals the next task involves the Black Lake. Meanwhile, Hermione launches a campaign to free house-elves through S.P.E.W., to Ron and Harry's amusement.",
    21: "The Yule Ball approaches, and Harry and Ron struggle to find dates. Harry asks Cho Chang but is rejected; Ron humiliates Fleur. Finally, Harry asks Parvati Patil and Ron reluctantly asks her twin Padma. The ball reveals a deep awkwardness in their teenage social skills.",
    22: "At the Yule Ball, the champions open the dancing, and the evening becomes a spectacle of teenage drama. Harry and Ron watch Hermione dance with Viktor Krum, causing Ron's jealousy to surface. Harry overhears a disturbing conversation between Snape and Karkaroff about something becoming clearer. Hagrid reveals his giant heritage to Madame Maxime.",
    23: "Rita Skeeter publishes a scandalous article about Hagrid's giant bloodline and Harry's supposed dark secrets. Hagrid, devastated, refuses to teach. Dumbledore and the trio convince him to return. Harry learns from Cedric, as repayment for the dragon tip, to take the golden egg into the prefects' bathroom and open it underwater.",
    24: "In the prefects' bathroom, Harry opens the egg underwater with help from Moaning Myrtle and hears the clue: something he treasures will be taken and he has one hour to retrieve it from the Black Lake. He realizes he must find a way to breathe underwater for an hour.",
    25: "Panicked the night before the second task, Harry is saved by Dobby, who gives him Gillyweed — enabling him to grow gills and breathe underwater. Harry dives into the Black Lake and discovers the champions must rescue their most treasured person: Ron, Hermione, Cho, and Fleur's little sister.",
    26: "Harry successfully rescues Ron with his gills, but also saves Fleur's sister when Fleur fails to complete the task. Harry's moral character earns him high marks, vaulting him to second place. The judges praise his courage and selflessness, even as Krum and Cedric finish ahead of him.",
    27: "Exploring the grounds, Harry runs into Sirius Black in his Animagus form as a large black dog. Sirius warns Harry about the growing danger at Hogwarts and reveals his suspicions about the mysterious events surrounding the Triwizard Tournament, urging Harry to be vigilant.",
    28: "During a late-night walk, Harry encounters a deranged Mr Crouch wandering the grounds, raving about doing something terrible and needing to warn Dumbledore. Harry runs to get Dumbledore, but when they return, Crouch has disappeared and Krum is found stunned nearby. Something sinister is happening at Hogwarts.",
    29: "Harry's scar continues to hurt, and he has another vivid dream — this time seeing Voldemort punish Wormtail for a mistake. He writes to Sirius about the dream. Dumbledore becomes increasingly concerned about Harry's scar and the connection it might represent.",
    30: "Dumbledore shows Harry the Pensieve, a magical basin for viewing memories. Harry witnesses trials from the past: Barty Crouch Jr, Ludo Bagman, and the Lestranges all accused of being Death Eaters. Most disturbingly, he sees Barty Crouch Jr convicted and sent to Azkaban by his own father.",
    31: "The third task takes place in a massive, dangerous maze on the Quidditch pitch. Harry and Cedric navigate the hedge maze together, overcoming obstacles and creatures. They reach the Triwizard Cup simultaneously and, in a gesture of fairness, agree to take it together — both reaching for the Cup at the same moment, which turns out to be a Portkey.",
    32: "The Cup transports Harry and Cedric to a graveyard. Wormtail appears with what looks like a baby — the weakened form of Voldemort. Wormtail kills Cedric instantly. Harry is tied to a gravestone as Wormtail performs a dark ritual using Harry's blood, a bone from Tom Riddle's grave, and his own severed hand. Lord Voldemort rises again.",
    33: "Voldemort summons his Death Eaters to the graveyard, berating them for their disloyalty. He duels Harry, but their wands connect due to sharing a Phoenix feather core — the rare Priori Incantatem effect. Ghostly echoes of Voldemort's victims emerge from his wand, including Harry's parents, telling him to hold on and flee.",
    34: "The echoes of the murdered — Cedric, Frank Bryce, Bertha Jorkins, Lily and James Potter — swirl around Harry, giving him the strength to break the connection and escape. Harry grabs Cedric's body and the Cup, Portkeying back to Hogwarts, where chaos erupts as everyone realizes what has happened.",
    35: "Harry is taken to Dumbledore's office, where he recounts the night's events. Moody pulls Harry away, and in a shocking twist, reveals he is actually Barty Crouch Jr — who has been impersonating the real Moody using Polyjuice Potion all year. Crouch Jr confesses he entered Harry's name in the Goblet and orchestrated the entire Portkey plot.",
    36: "Dumbledore, McGonagall, and Snape confront Barty Crouch Jr, who is forced to confess under Veritaserum. The Minister for Magic, Cornelius Fudge, refuses to believe that Voldemort has returned and has a Dementor administer the Kiss to Crouch Jr, destroying crucial evidence. Dumbledore immediately begins organizing resistance against Voldemort.",
    37: "At the end-of-year feast, Dumbledore announces Cedric's death and, against the Ministry's wishes, declares that Lord Voldemort has returned. Harry, Hermione, and the Weasleys leave Hogwarts. Harry gives his Triwizard winnings to Fred and George to start their joke shop, and prepares to face the summer — knowing the wizarding world will never be the same.",
}

def main():
    chapters = sorted(CORPUS.glob("hp04-ch*.md"))
    print(f"Injecting summaries into {len(chapters)} chapters...")
    for ch_path in chapters:
        m = re.match(r"hp04-ch(\d+)\.md", ch_path.name)
        if not m: continue
        no = int(m.group(1))
        s = SUMMARIES.get(no)
        if not s:
            print(f"  SKIP {ch_path.name}: no summary")
            continue
        c = ch_path.read_text(encoding="utf-8")
        parts = c.split("---", 2)
        if len(parts) < 3:
            print(f"  SKIP {ch_path.name}: bad fm"); continue
        if re.search(r"^summary:", parts[1], re.MULTILINE):
            print(f"  SKIP {ch_path.name}: exists"); continue
        ch_path.write_text(f"---\n{parts[1].rstrip()}\nsummary: \"{s}\"\n---{parts[2]}", encoding="utf-8")
        print(f"  OK {ch_path.name}")
    print("Done.")

if __name__ == "__main__":
    main()
