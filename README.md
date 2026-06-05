# GreenPulse Emergency Green Corridor

A Flask-based smart-city emergency traffic control demo.

## Main visible dashboard features
- Live city map with road-only vehicle movement
- Four emergency vehicles: 2 ambulances, 1 police car, 1 fire truck
- Emergency request controls
- Emergency fleet status
- Live monitoring cards
- Emergency queue
- Live junction status table
- IoT device health
- Emergency activity timeline
- Analytics and printable emergency report

## Internal logic kept hidden from user view
- Priority and severity calculation
- Same-route shared green corridor decision
- Different-direction conflict handling
- Emergency preemption signal sequence
- Queue priority sorting
- Fixed demo animation speed

## Run locally
```bash
pip install -r requirements.txt
python app.py
```

Open: http://127.0.0.1:5000

## Test
```bash
python tests/test_greenpulse_api.py
```
