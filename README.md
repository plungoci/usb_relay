# USB Relay Controller

**USB Relay Controller** este o aplicație desktop scrisă în Python cu **PySide6 (Qt)**, pentru controlul rapid al mai multor module USB Relay. Comunicarea cu hardware-ul se face direct prin biblioteca nativă **`USB_RELAY_DEVICE.dll`** (USB Relay Device Library v2), inclusă în directorul `lib/`.

Fereastra are două file:

- **Control relee** — scanează plăcile conectate, alegi câte folosești (1-4) și comanzi fiecare canal;
- **Schimbă ID placă** — varianta grafică a utilitarului `change_usbrelay_id.py`.

## Ce face aplicația

La pornire, aplicația scanează automat plăcile conectate și le afișează cu serialul real și numărul real de canale. Nimic nu este presupus: serialele și numărul de relee (1, 2, 4 sau 8 canale) vin din bibliotecă, iar starea butoanelor este citită din hardware după fiecare comandă.

Din lista **Plăci de relee folosite** alegi câte plăci comanzi: 1, 2, 3 sau 4. Dacă ai selectat mai multe plăci decât sunt detectate, pozițiile rămase apar ca **neconectată**, iar bara de stare îți spune câte plăci s-au găsit.

Fiecare releu are propriul buton ON/OFF, iar starea lui este evidențiată vizual prin culoare:

- **ON** — buton verde, pentru releu activat;
- **OFF** — buton gri, pentru releu dezactivat.

Butoanele din bara de sus acoperă operațiile rapide:

- **Scanează plăci** — recitește lista de plăci conectate;
- **Citește starea** — resincronizează interfața cu starea reală a releelor;
- **ALL ON** / **ALL OFF** — pornesc sau opresc toate releele de pe plăcile active.

Comenzile globale se aplică doar plăcilor selectate, așa că nu se trimit comenzi către plăci pe care nu le folosești.

## Cum comunică cu hardware-ul

Fișierul `usb_relay_lib.py` este un binding `ctypes` peste biblioteca nativă și expune două niveluri:

- `UsbRelayLibrary` — reflectă unu-la-unu funcțiile din `usb_relay_device.h` (`usb_relay_init`, `usb_relay_device_enumerate`, `usb_relay_device_open_with_serial_number`, comenzile pe canale, `usb_relay_device_get_status_bitmap`);
- `RelayController` — ține deschise handle-urile plăcilor, traduce masca de biți în stări și oferă operații pe o placă sau pe mai multe.

Două constrângeri din documentația bibliotecii sunt tratate explicit în cod:

- **biblioteca nu este thread-safe** — toate apelurile trec printr-un singur thread de lucru (`RelayService`), iar rezultatele ajung în interfață prin semnale Qt, deci interfața nu se blochează;
- **biblioteca nu detectează conectarea/deconectarea la cald** — de aceea există butonul **Scanează plăci**, iar lista se reîmprospătează doar la cerere.

Codurile de retur documentate în header (`0` succes, `1` eroare, `2` index invalid) sunt transformate în mesaje clare, afișate în interfață.

## Schimbarea ID-ului din interfață

Fila **Schimbă ID placă** oferă aceleași operații ca utilitarul din linia de comandă, dar cu mouse-ul:

- butonul **Reîmprospătează lista** enumeră plăcile și arată pentru fiecare ID-ul și numărul de canale;
- lista **Placă țintă** îți lasă să alegi exact placa pe care scrii; dacă rămâne pe „placă unică conectată", scrierea se face doar când e conectată o singură placă, altfel aplicația refuză explicit și îți spune ce plăci a găsit;
- câmpul **ID nou** acceptă doar caractere alfanumerice ASCII și maximum 5 caractere, iar textul este transformat automat în majuscule;
- butonul **Scrie ID pe placă** cere o confirmare, apoi scrie noul serial;
- după scriere, aplicația îți amintește să deconectezi și să reconectezi placa, iar fila de control cere o rescanare.

Scrierea ID-ului se face printr-un raport HID de tip *feature*, pentru că biblioteca nativă nu expune o funcție de setare a serialului. Pe **Windows nu este nevoie de nicio dependință în plus**: `hid_backend.py` folosește direct API-ul din sistem (`setupapi.dll` pentru enumerare, `hid.dll` pentru rapoarte). Pe alte sisteme se folosește pachetul Python `hid`, dacă este instalat.

Plăcile își țin ID-ul în primii octeți ai raportului de feature, așa că aplicația poate identifica fiecare placă și scrie pe cea aleasă. Înainte de scriere, handle-urile deschise de biblioteca de relee sunt eliberate, ca placa să nu rămână ocupată.

## Utilitar în linia de comandă

Fișierul `change_usbrelay_id.py` poate fi folosit și direct, din terminal:

- listează plăcile detectate prin aceeași bibliotecă nativă;
- acceptă ID-uri ASCII alfanumerice de maximum 5 caractere;
- construiește raportul HID într-o funcție separată, mai ușor de testat și întreținut;
- expune `validate_id` și `change_id`, funcțiile refolosite de interfața grafică;
- rulează doar când fișierul este executat direct, datorită blocului `if __name__ == "__main__"`.

> Recomandare: conectează o singură placă atunci când schimbi ID-ul, apoi deconectează și reconectează placa înainte de verificare.

## De ce este utilă

Acest controller este potrivit pentru scenarii în care este nevoie de comutarea rapidă și organizată a mai multor ieșiri electrice: bancuri de testare, automatizări de laborator, prototipuri hardware, validări de echipamente sau control local pentru dispozitive conectate prin relee USB.

Pentru că apelurile se fac direct în biblioteca nativă, nu prin pornirea unui proces extern pentru fiecare comandă, reacția este mai rapidă, iar erorile ajung direct în interfață.

## Funcționalități principale

- interfață grafică intuitivă, bazată pe PySide6 (Qt);
- detectarea automată a plăcilor conectate, cu serialul și numărul real de canale;
- selectarea numărului de plăci folosite: 1, 2, 3 sau 4;
- suport pentru plăci cu 1, 2, 4 sau 8 canale;
- control individual pentru fiecare releu;
- comenzi globale pentru activarea sau dezactivarea releelor de pe plăcile active;
- citirea stării reale a releelor din hardware;
- schimbarea ID-ului unei plăci direct din interfață;
- mesaje de eroare clare, plus bară de stare cu ultima acțiune executată;
- utilitar separat, în linia de comandă, pentru schimbarea ID-ului plăcilor.

## Cerințe

- Windows, cu `USB_RELAY_DEVICE.dll` din `lib/` (versiunea inclusă este pe **64 de biți**);
- Python 3 pe **64 de biți**, ca să corespundă arhitecturii DLL-ului;
- pachetul Python `PySide6` pentru interfața grafică;
- eventual pachetul VC++ redistributable, cerut de DLL.

Pe Windows nu este nevoie de pachetul `hid` sau de `hidapi.dll`: schimbarea ID-ului folosește stiva HID a sistemului. Pachetul `hid` este necesar doar dacă rulezi pe alt sistem de operare.

```bash
pip install -r requirements.txt
```

## Structura proiectului

| Fișier | Rol |
| --- | --- |
| `relay_gui.py` | interfața PySide6 și threadul de lucru |
| `usb_relay_lib.py` | binding `ctypes` peste biblioteca nativă |
| `change_usbrelay_id.py` | schimbarea ID-ului (interfață + linie de comandă) |
| `hid_backend.py` | acces HID nativ pe Windows, cu rezervă pe pachetul `hid` |
| `lib/USB_RELAY_DEVICE.dll` | biblioteca nativă, 64 de biți |
| `lib/usb_relay_device.h`, `lib/usb_relay_device.lib` | header și import library, pentru integrări C/C++ |
| `lib/Readme_USBRelayDLL.md` | documentația originală a bibliotecii |

## Rulare interfață grafică

```bash
python relay_gui.py
```

După pornire, aplicația scanează plăcile conectate. Alege câte plăci folosești, apoi apasă pe butonul unui releu pentru a-i schimba starea sau folosește butoanele globale pentru control simultan.

## Schimbarea ID-ului unei plăci din terminal

```bash
python change_usbrelay_id.py
```

Urmează instrucțiunile afișate în terminal. Pentru ieșire, introdu `Q`, `QUIT` sau `EXIT`.

## Depanare

- **„Nu pot încărca biblioteca USB Relay"** — verifică dacă `USB_RELAY_DEVICE.dll` este în `lib/` și dacă arhitectura Python (32/64 de biți) se potrivește cu cea a DLL-ului. Mesajul de eroare afișat de aplicație spune exact unde a căutat.
- **DLL într-o altă locație** — setează variabila de mediu `USB_RELAY_DLL` către calea bibliotecii; are prioritate față de căutarea automată.
- **Placa nu apare în listă** — biblioteca nu detectează conectarea la cald, deci apasă **Scanează plăci** după ce ai conectat placa.
- **„Sunt conectate N plăci"** — alege placa din lista **Placă țintă** sau lasă conectată o singură placă.
- **Nu pot deschide placa pentru scriere** — închide alte programe care folosesc placa și încearcă din nou.
- **Pe alt sistem decât Windows** — scrierea ID-ului cere pachetul `hid` împreună cu biblioteca nativă `hidapi`; pe Windows nu ai nevoie de niciuna.

## Personalizare

Numărul maxim de plăci selectabile și numărul implicit sunt date de constantele `MAX_BOARD_COUNT` și `DEFAULT_BOARD_COUNT` din `relay_gui.py`. Numărul de canale nu se configurează: vine de la fiecare placă, prin `usb_relay_device_get_num_relays`.
