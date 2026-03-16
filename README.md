# Lottery Intelligence Hub

Web app pronta per deploy con due pagine separate:

- `/euromillions`
- `/superenalotto`

## Avvio locale

```bash
pip install -r requirements.txt
python app.py
```

Poi apri:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/euromillions
- http://127.0.0.1:8000/superenalotto

## Deploy su Render

1. Crea un repository GitHub e carica tutti i file di questa cartella.
2. Su Render scegli **New + > Web Service**.
3. Collega il repository.
4. Render leggerà automaticamente `render.yaml`.
5. Quando il deploy finisce, avrai un link pubblico.

## Note

- La web app include il CSV iniziale EuroMillions e gli archivi `.xls` SuperEnalotto.
- Ogni dashboard prova ad aggiornarsi dalla fonte ufficiale quando viene aperta.
- Se la fonte ufficiale non risponde, usa la cache locale.
- È uno strumento statistico, non una garanzia di vincita.
