Moduri FS22 convertite pentru Farming Simulator 25: **DT-75 Pack** si **T-150 Gus**.

## Cum instalezi
1. Descarca ambele fisiere de mai jos: `FS25_DT_Pack.zip` si `FS25_T150_Gus.zip`.
2. Sterge mai intai orice copie veche sau duplicat cu `(1)` in nume
   (ex. `FS25_DT_Pack (1).zip`). Numele trebuie sa fie exact `FS25_DT_Pack.zip`
   si `FS25_T150_Gus.zip` - jocul ignora fisierele cu spatii, paranteze sau alte
   caractere in afara de litere, cifre si `_`.
3. Copiaza-le in folderul de mods al jocului:
   `Documents\My Games\FarmingSimulator2025\mods`
4. Porneste jocul si incarca o salvarea. Categoria din magazin: `ДТ Пак` (DT-75)
   si `HTZ` (T-150).
5. In `log.txt` trebuie sa apara `Available mod: ... FS25_DT_Pack` si
   `Available mod: ... FS25_T150_Gus` - daca nu apar, modul nu s-a incarcat.

## Versiuni
* DT-75 Pack: **1.0.0.4**
* T-150 Gus: **1.0.0.2**

## Ce contine conversia
* `descVersion` 104 si XML-uri actualizate pentru FS25.
* Coliziuni migrate de la `collisionMask` (FS22) la perechea
  `collisionFilterGroup` / `collisionFilterMask` (FS25) - altfel piesele nu ating
  nimic si vehiculul cade prin harta.
* Sunete: numele de template-uri care existau doar in FS22 (`SWITCH_01`,
  `ATTACH_01`, `MEDIUM_TRACTOR_MOTOR_*`, `WATER_SPLASH_01`, `ROLLBELT_LOOP` etc.)
  au fost inlocuite cu echivalentele FS25, iar referintele de fisier audio au fost
  reparate (modul livra `.ogg` dar XML-ul cerea `.wav` - de aceea ramaneau mute
  motorul si senilele).
* Shader-e FS25 (`colorMat`) pentru vopsirea FS22 + `materialSlotName` in
  configuratiile de culoare.
* Atribute FS22 redenumite pentru FS25 (`softShadows*`, `aiReverserNode`,
  `spineRotationOffset`, `supportsWheelSink`, `straighteningFactor`,
  `storeCategories` etc.).
* Iconite de magazin reparate (`.png` -> `.dds`) si toate referintele de fisiere
  verificate automat.

## Verificare automata (build curent)
Fiecare build este verificat automat; rezultatul complet este in
`transfer/_selftest.txt`:

* `FS25_DT_Pack` - **11 verificari PASS, 0 avertismente, 0 erori**
* `FS25_T150_Gus` - **11 verificari PASS, 0 avertismente, 0 erori**

Verificarile acopera: parsare XML, validare fata de schemele FS25
(`modDesc.xsd`, `vehicle.xsd`, `i3d-1.6.xsd`: 0 violari noi), referinte de fisiere
(0 lipsa), comparatie 1:1 cu arhiva FS22 (173 / 224 fisiere, 0 pierdute, 0 noduri
pierdute), coliziuni, nume de sunete (0 nume FS22 ramase, 0 necunoscute),
specializari, shader-e, tipuri de cuplare si **1526 / 1293 de referinte de nod
rezolvate in i3d (0 nerezolvate)**.

Daca apar probleme in joc, trimite `log.txt`
(`Documents\My Games\FarmingSimulator2025\log.txt`) si o poza cu problema.
