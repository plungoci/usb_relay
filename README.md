# USB Relay Controller

**USB Relay Controller** este o aplicație desktop simplă, construită în Python cu Tkinter, pentru controlul rapid al mai multor module USB Relay. Interfața oferă o vedere clară asupra fiecărei plăci și a fiecărui releu, astfel încât pornirea sau oprirea circuitelor conectate să fie la un click distanță.

## Ce face aplicația

Aplicația controlează patru plăci de relee, identificate prin serialele `RLY01`, `RLY02`, `RLY03` și `RLY04`, fiecare având câte patru relee. Fiecare releu are propriul buton ON/OFF, iar starea lui este evidențiată vizual prin culoare:

- **ON** — buton verde, pentru releu activat;
- **OFF** — buton gri, pentru releu dezactivat.

Pentru operații rapide, aplicația include și două comenzi globale:

- **ALL ON** — pornește toate releele de pe toate plăcile;
- **ALL OFF** — oprește toate releele de pe toate plăcile.

## Optimizări incluse

- comenzile individuale sunt executate în fundal, astfel încât interfața Tkinter nu se blochează în timpul comunicării cu `usbrelay.exe`;
- comenzile globale rulează în paralel pentru toate releele configurate;
- butoanele sunt dezactivate temporar cât timp comanda asociată este în execuție, pentru a preveni apăsările repetate accidentale;
- starea din interfață este actualizată numai pentru comenzile executate cu succes;
- erorile returnate de `usbrelay.exe` sunt afișate în consolă pentru depanare mai ușoară.

## Utilitar pentru schimbarea ID-ului

Fișierul `change_usbrelay_id.py` ajută la schimbarea serialului unei plăci USB Relay. Scriptul:

- listează plăcile detectate cu `usbrelay.exe -list`;
- acceptă ID-uri ASCII alfanumerice de maximum 5 caractere;
- construiește raportul HID într-o funcție separată, mai ușor de testat și întreținut;
- rulează doar când fișierul este executat direct, datorită blocului `if __name__ == "__main__"`.

> Recomandare: conectează o singură placă atunci când schimbi ID-ul, apoi deconectează și reconectează placa înainte de verificare.

## De ce este utilă

Acest controller este potrivit pentru scenarii în care este nevoie de comutarea rapidă și organizată a mai multor ieșiri electrice: bancuri de testare, automatizări de laborator, prototipuri hardware, validări de echipamente sau control local pentru dispozitive conectate prin relee USB.

Prin folosirea comenzilor în paralel atunci când se schimbă starea tuturor releelor, aplicația reduce timpul de reacție și oferă o experiență fluidă chiar și atunci când sunt controlate 16 relee simultan.

## Funcționalități principale

- interfață grafică intuitivă, bazată pe Tkinter;
- control individual pentru fiecare releu;
- comenzi globale pentru activarea sau dezactivarea tuturor releelor;
- afișarea stării curente direct pe butoane;
- integrare cu executabilul `usbrelay.exe` pentru trimiterea comenzilor către hardware;
- mesaje de eroare clare atunci când un releu nu poate fi controlat;
- utilitar separat pentru schimbarea ID-ului plăcilor.

## Cerințe

- Python 3;
- Tkinter disponibil în instalarea Python;
- pachetul Python `hid` pentru `change_usbrelay_id.py`;
- `usbrelay.exe` accesibil din directorul aplicației sau din `PATH`;
- module USB Relay configurate cu serialele definite în `relay_gui.py`.

## Rulare interfață grafică

```bash
python relay_gui.py
```

După pornire, se deschide fereastra **USB Relay Controller**, unde fiecare placă are propriul grup de controale. Apasă pe butonul unui releu pentru a-i schimba starea sau folosește butoanele globale pentru control simultan.

## Schimbarea ID-ului unei plăci

```bash
python change_usbrelay_id.py
```

Urmează instrucțiunile afișate în terminal. Pentru ieșire, introdu `Q`, `QUIT` sau `EXIT`.

## Personalizare

Lista plăcilor și numărul de relee per placă pot fi ajustate direct în `relay_gui.py`, prin modificarea constantelor `BOARDS` și `RELAYS_PER_BOARD`.
