"""Estimate a CIBC conversion using an explicitly supplied reference rate."""
import argparse
import json
from pathlib import Path
from model import DIRECTIONS, predict


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--direction',choices=DIRECTIONS,required=True)
    parser.add_argument('--reference-rate',type=float,required=True)
    parser.add_argument('--usd',type=float,required=True)
    parser.add_argument('--model',type=Path,default=Path(__file__).resolve().parent/'artifacts/model.json')
    args=parser.parse_args()
    model=json.loads(args.model.read_text())
    print(json.dumps(predict(model,args.direction,args.reference_rate,args.usd),indent=2))


if __name__ == '__main__':
    main()
