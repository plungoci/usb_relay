# USB Relay Controller

**USB Relay Controller** este o aplicație desktop simplă, construită în Python cu **PySide6 (Qt)**, pentru controlul rapid al mai multor module USB Relay. Interfața oferă o vedere clară asupra fiecărei plăci și a fiecărui releu, astfel încât pornirea sau oprirea circuitelor conectate să fie la un click distanță.

Fereastra are două file:

- **Control relee** — alegi câte plăci folosești (1-4) și comanzi fiecare releu;
- **Schimbă ID placă** — varianta grafică a utilitarului `change_usbrelay_id.py`.

## Ce face aplicația

Aplicația controlează până la patru plăci de relee, identificate prin serialele `RLY01`, `RLY02`, `RLY03` și `RLY04`, fiecare având câte patru relee. Din lista **Plăci de relee folosite** alegi câte plăci sunt conectate (1, 2, 3 sau 4), iar interfața afișează doar plăcile selectate. Fiecare releu are propriul buton ON/OFF, iar starea lui este evidențiată vizual prin culoare:

- **ON** — buton verde, pentru releu activat;
- **OFF** — buton gri, pentru releu dezactivat.

Pentru operații rapide, aplicația include și două comenzi globale:

- **ALL ON** — pornește toate releele de pe plăcile active;
- **ALL OFF** — oprește toate releele de pe plăcile active.

Comenzile globale se aplică doar plăcilor selectate, așa că nu se trimit comenzi către plăci care nu sunt conectate.

## Optimizări incluse

- comenzile individuale sunt executate în fundal, pe `QThreadPool`, astfel încât interfața Qt nu se blochează în timpul comunicării cu `usbrelay.exe`;
- comenzile globale rulează în paralel pentru toate releele configurate;
- butoanele sunt dezactivate temporar cât timp comanda asociată este în execuție, pentru a preveni apăsările repetate accidentale;
- starea din interfață este actualizată numai pentru comenzile executate cu succes;
- erorile returnate de `usbrelay.exe` sunt afișate în interfață, atât în bara de stare, cât și într-un mesaj cu detalii.

## Schimbarea ID-ului din interfață

Fila **Schimbă ID placă** oferă aceleași operații ca utilitarul din linia de comandă, dar cu mouse-ul:

- butonul **Reîmprospătează lista** rulează `usbrelay.exe -list` și afișează plăcile detectate;
- câmpul **ID nou** acceptă doar caractere alfanumerice ASCII și maximum 5 caractere, iar textul este transformat automat în majuscule;
- butonul **Scrie ID pe placă** cere o confirmare, apoi trimite raportul HID către placă;
- după scriere, aplicația îți amintește să deconectezi și să reconectezi placa, ca să poți verifica noul serial.

Codul din spate este reutilizat din `change_usbrelay_id.py`, deci interfața și linia de comandă se comportă identic.

## Utilitar în linia de comandă

Fișierul `change_usbrelay_id.py` poate fi folosit și direct, din terminal. Scriptul:

- listează plăcile detectate cu `usbrelay.exe -list`;
- acceptă ID-uri ASCII alfanumerice de maximum 5 caractere;
- construiește raportul HID într-o funcție separată, mai ușor de testat și întreținut;
- expune `list_relays_output`, `validate_id` și `change_id`, funcțiile refolosite de interfața grafică;
- rulează doar când fișierul este executat direct, datorită blocului `if __name__ == "__main__"`.

> Recomandare: conectează o singură placă atunci când schimbi ID-ul, apoi deconectează și reconectează placa înainte de verificare.

## De ce este utilă

Acest controller este potrivit pentru scenarii în care este nevoie de comutarea rapidă și organizată a mai multor ieșiri electrice: bancuri de testare, automatizări de laborator, prototipuri hardware, validări de echipamente sau control local pentru dispozitive conectate prin relee USB.

Prin folosirea comenzilor în paralel atunci când se schimbă starea tuturor releelor, aplicația reduce timpul de reacție și oferă o experiență fluidă chiar și atunci când sunt controlate 16 relee simultan.

## Funcționalități principale

- interfață grafică intuitivă, bazată pe PySide6 (Qt);
- selectarea numărului de plăci folosite: 1, 2, 3 sau 4;
- control individual pentru fiecare releu;
- comenzi globale pentru activarea sau dezactivarea releelor de pe plăcile active;
- schimbarea ID-ului unei plăci direct din interfață;
- afișarea stării curente direct pe butoane;
- integrare cu executabilul `usbrelay.exe` pentru trimiterea comenzilor către hardware;
- mesaje de eroare clare atunci când un releu nu poate fi controlat;
- bară de stare cu ultima acțiune executată;
- utilitar separat, în linia de comandă, pentru schimbarea ID-ului plăcilor.

## Cerințe

- Python 3;
- pachetul Python `PySide6` pentru interfața grafică (`pip install PySide6`);
- pachetul Python `hid` pentru schimbarea ID-ului (`pip install hid`);
- `usbrelay.exe` accesibil din directorul aplicației sau din `PATH`;
- module USB Relay configurate cu serialele definite în `relay_gui.py`.

## Rulare interfață grafică

```bash
python relay_gui.py
```

După pornire, se deschide fereastra **USB Relay Controller**. Alege mai întâi câte plăci folosești, apoi apasă pe butonul unui releu pentru a-i schimba starea sau folosește butoanele globale pentru control simultan.

## Schimbarea ID-ului unei plăci din terminal

```bash
python change_usbrelay_id.py
```

Urmează instrucțiunile afișate în terminal. Pentru ieșire, introdu `Q`, `QUIT` sau `EXIT`.

## Personalizare

Serialele plăcilor și numărul de relee per placă pot fi ajustate direct în `relay_gui.py`, prin modificarea constantelor `ALL_BOARDS` și `RELAYS_PER_BOARD`. Numărul de plăci oferit în listă se adaptează automat la lungimea lui `ALL_BOARDS`, iar `DEFAULT_BOARD_COUNT` stabilește câte plăci sunt selectate la pornire.
