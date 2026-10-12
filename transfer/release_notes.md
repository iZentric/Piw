Moduri FS22 convertite pentru Farming Simulator 25: **DT-75 Pack** si **T-150 Gus**.

## Cum instalezi
1. Descarca ambele fisiere de mai jos: `FS25_DT_Pack.zip` si `FS25_T150_Gus.zip`.
2. Sterge mai intai orice copie veche sau duplicat cu `(1)` in nume
   (ex. `FS25_DT_Pack (1).zip`). Jocul ignora fisierele care contin spatii, paranteze
   sau alte caractere in afara de litere, cifre si `_`; numele trebuie sa fie exact
   `FS25_DT_Pack.zip` si `FS25_T150_Gus.zip`.
3. Copiaza-le in folderul de mods al jocului:
   `Documents\My Games\FarmingSimulator2025\mods`
4. Porneste jocul si incarca o salvarea; modurile apar in magazin la categoria
   `ДТ Пак` (DT-75) si `HTZ` (T-150).

In `log.txt` trebuie sa apara liniile `Available mod: ... FS25_DT_Pack` si
`Available mod: ... FS25_T150_Gus` - daca nu apar, modul nu a fost incarcat.

## Versiuni
* DT-75 Pack: **1.0.0.4**
* T-150 Gus: **1.0.0.2**

## Ce contine conversia
* `descVersion` 104 si XML-uri actualizate pentru FS25.
* Coliziuni migrate de la `collisionMask` (FS22) la perechea
  `collisionFilterGroup` / `collisionFilterMask` (FS25) - altfel piesele nu mai
  ating nimic si vehiculul cade prin harta.
* Sunete: numele de template-uri FS22 inlocuite cu echivalentele FS25, ca motorul,
  cutia si sunetele de lucru sa porneasca.
* Shader-e FS25 (`colorMat`) pentru vopsirea FS22 + `materialSlotName` in
  configuratiile de culoare.
* Atribute FS22 redenumite pentru FS25 (`softShadows*`, `aiReverserNode`,
  `spineRotationOffset`, `supportsWheelSink`, `straighteningFactor` etc.).
* Referinte de fisiere verificate automat (0 referinte lipsa) si iconite de
  magazin reparate.

## Verificare automata
Fiecare build este verificat automat (`transfer/_selftest.txt`): parsare XML,
validare fata de schemele FS25 (`vehicle.xsd`, `modDesc.xsd`, `i3d-1.6.xsd`),
referinte de fisiere, coliziuni, sunete, specializari, shader-e si comparatie
1:1 cu arhiva originala FS22 (niciun fisier/numar de nod pierdut).

Daca apar probleme in joc, trimite `log.txt`
(`Documents\My Games\FarmingSimulator2025\log.txt`).
