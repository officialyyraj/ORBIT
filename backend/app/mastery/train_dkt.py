import argparse
from app.db.session import SessionLocal
from app.mastery.dkt import DKTStrategy


def main():
    parser = argparse.ArgumentParser(description='Train the lightweight ORBIT DKT checkpoint offline.')
    parser.add_argument('--output', default='dkt_checkpoint.json')
    parser.add_argument('--epochs', type=int, default=8)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        model = DKTStrategy()
        metrics = model.fit(db, epochs=args.epochs)
        model.save(args.output)
        print({'checkpoint': args.output, **metrics})
    finally:
        db.close()

if __name__ == '__main__':
    main()
