# Interview — product owner (also the builder and the only known user), 2026-09-05

Discovery session run with `om-discover`, four question rounds, conducted in Polish. Single respondent: Michal Klosinski. Quotes are verbatim, typos included; the English after each is a translation, not a source. This note is the `[INTERVIEW]` source cited by `.ai/specs/product-brief.md`; decisions taken here are recorded separately under `../decisions/`.

## Situation the person was in when the problem showed up

Planning his own trips. No specific trip was walked through, so the situation is described in general terms only — this is the weakest part of the material and is why the current-state flow in the brief is marked thin.

## What they did about it, step by step

Round four, asked where the plan for the last real trip actually lived, tool by tool:

> "w głowie, na mailu; trochę w excelu"

In his head, in his e-mail, and partly in a spreadsheet. Nothing else was recorded: no sequence of steps, no moment where it broke, no description of what happened when somebody asked to see the plan.

## What it cost them (time, money, risk), in their words

Not established. The owner gave no frequency, no time lost and no incident. The brief records this gap explicitly rather than filling it.

## What they tried before, and why it was not enough

Not established beyond the three places above.

## What would make them say the problem is gone

Round one:

> "zaplanowałem w tym jedną podróż to pierwszy cel."

Planning one trip in it is the first goal. Round three fixed the trip and the year (Malaysia, October 2026); round four confirmed the check date 2026-09-30 after the agent's invented date had been removed from the draft:

> "30.09 jest dobrą datą"

## Verbatim quotes worth keeping

Opening statement, unprompted, describing the product:

> "Robię aplikację do planowania podróży. Zaczyna się od podania dat i ew. punktu startu (dokąd lecę/jadę) i powrotu. Można podać przez formularz lub przez chat. Główny widok to lini czasu gdzie mogę planować co będę robić, gdzie będę mieszkać itp. Można mieć plany w stanie 'do zrobienia/zarezerwowania' lub już zaplnaowane (opcjonalnie z podpiętymi rezerwacjami). Na każdym etapie mogę w chatcie napisać co chcę zmienić/sprawdzić/dodać. Lub rozklikać dany dzień i przejść do edycji szczegółów. Mogę załączać pliki/obrazki etc."

Round one, who it is for:

> "ja i znajomi"

Round one, what hurts today — the two problems P1 and P2 of the brief:

> "brak jasnego overview co zostało już załatwione, co zostało; możlwiości podzelenia się z innymi stanem planów"

Round one, whether the app searches the real world:

> "przede wszystkim planowanie; cała reszta to dodatek - nie musi sam szukać; może sugerować pewne rzeczy ze swojej wiedzy albo przez web search"

Round one, the smallest first version, choosing between a manual timeline (a), chat generating a draft plan (b), and a reservations inbox (c):

> "zdecydiwanie a"

Round one, solo or with companions:

> "Najpierw główny edytor, i podgląd, z ew. możliwością skomentowania, wysłania sugestii"

Round one, kill criteria:

> "brak, świadomie"

Round one, non-goals:

> "wszystkie opcje można dodać potem, żadna nie musi być teraz, żadnej nie wykluczam"

Round one, unprompted, pointing at the design material:

> "q ~/sync znajduje się planner_podrozy.zip -- wstępny design aplikacji; do dostostosowania w trakcie prac"

Round two, product name, statuses, multi-stop, money, sharing, the trip, kill criteria again, and the exclusion list:

> "Q9: Smart Trip Planner"
> "Q10: 3"
> "Q11: Zdecydowanie wieloprzystankowość."
> "Q12: Jeżeli informacja będzie dostępna (np. z uploadu rezerwacji) to warto ją trzymać; w przyszłości rozliczanie może być istotną funkcją"
> "Q13: Wchpdzi przez magic linka."
> "Q14: Najchętniej: Malezja w październiku"
> "q15: Jak będę dłubał to moja sprawa. Jak nie będę używał to pewnie zostawię. Nie twój problem."
> "Q16: Zgonie z Twoimi sugestiami"

Round three, three clarifications answered by choosing from offered options: "Nic nie wykluczam" (superseding the Q16 acceptance), "październik 2026", "E-mail i hasło".

Round four, after the draft brief was reviewed cold and its fabrications removed:

> "q2: do zaplanowania, do zarezerwowania, gotowe - licza sie 2 ostatnie"
> "q3: jeden dla projekty, read only w v1"
> "q4: to będzie stało w internecie od dnia 1 - autoryzacja to must have"
> "q5: na początek dla mnie, jak mi się spodoba może dla większej ilości osób"

## What they explicitly did not care about

- A stop condition for the project: "nie twój problem". Recorded as D13.
- Testing whether anyone else has the problem before building: accepted as an open assumption, D15.

## Interviewer's own remarks (kept separate from what was said)

- Two answers in this session were the agent's proposals ratified by the owner rather than his own initiative: the count of three statuses (round two, "3") and the exclusion list of round two, which he then reversed in round three. Both are flagged as such in their decision records.
- The first draft of the brief invented a current-state story (spreadsheets, e-mails, browser tabs, "only in his head"), invented the three status names, and invented the 2026-09-30 check date. A cold review caught all three; the fabrications were removed and the questions put back to the owner, whose answers are the round-four quotes above. Two of the three came back different from the invention — which is the argument for asking rather than filling gaps.
- The design export the owner supplied is his own commissioned mockup, so it evidences his beliefs about the product, not demand for it. It is cited in the brief as `[DOCUMENT]` for what it contains, never as evidence that anyone needs the thing.
- No benchmark was checked: this session had no network access. That gap is on the brief's collection plan.
