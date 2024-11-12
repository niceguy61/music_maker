![N|Solid](https://capsule-render.vercel.app/api?type=waving&color=auto&height=200&section=header&text=LofiMusicPlaylistGenerator&fontSize=60)

## example
#### https://www.youtube.com/@OfficeLofiatNight

# 🎵 Lofi Music Playlist Generator
##### 자동으로 로파이 음악 플레이리스트를 생성하고 유튜브 업로드를 위한 챕터와 설명을 만드는 프로젝트입니다.

## 📋 프로젝트 소개
### 생성 배경
- 로파이 음악 플레이리스트 제작 자동화 필요
- 반복적인 유튜브 콘텐츠 생성 작업 최소화
- 트랙 중복 사용 방지 및 효율적인 음원 관리

## ✨ 주요 기능
- 음원 파일 자동 분석 (BPM, 장르, 음악적 특성)
- 스마트 플레이리스트 생성 (BPM 흐름, 장르 밸런스 고려)
- 유튜브 챕터 자동 생성 (SRT, TXT 포맷)
- AWS Bedrock Claude를 활용한 콘텐츠 설명 생성
- 트랙 사용 이력 관리

## 🛠 기술 스택
- Python 3.x
- AWS Bedrock (Claude 3 Sonnet)
- librosa (음원 분석)
- pandas (데이터 관리)
- boto3 (AWS SDK)

## 📁 프로젝트 구조
```
text
project_root/
├── data/
│   ├── raw/                # 원본 음원 파일
│   ├── playlists/          # 생성된 플레이리스트
│   ├── history/            # 트랙 사용 이력
│   └── metadata/           # 트랙 메타데이터
├── src/
│   ├── analyzer.py         # 음원 분석
│   ├── playlist_generator.py # 플레이리스트 생성
│   ├── create_track.py     # 메인 실행 파일
│   └── utils.py           # 유틸리티 함수
└── logs/                   # 로그 파일
```
## 📂 음원 폴더 구조
```
text
F:/audio_lofi_jazz/reference/
├── 1st/                   # 첫 번째 에피소드
├── 2nd/                   # 두 번째 에피소드
├── 3rd/                   # 세 번째 에피소드
...
└── temp/                  # 임시 파일
```

## 💻 사용 방법
#### 환경 설정
```bash
pip install -r requirements.txt
```

#### AWS 자격 증명 설정
```bash
aws configure sso
```

#### 음원 분석 실행
```bash
python create_track.py
```

#### 특정 에피소드 재생성
```bash
python create_track.py 17th
```

#### 📊 데이터 구조
```
tracks.csv
track_id: 트랙 고유 ID
title: 곡 제목
artist: 아티스트
bpm: 템포
duration_ms: 재생 시간
genre: 장르
sub_genre: 서브 장르
track_episodes.csv
track_episode_id: 에피소드 내 트랙 ID
track_id: 트랙 참조 ID
episode_id: 에피소드 참조 ID
order_in_episode: 재생 순서
```

#### 🔄 워크플로우
- 음원 파일 분석
- 메타데이터 추출 및 저장
- 플레이리스트 생성 알고리즘 실행
- 유튜브 콘텐츠 자동 생성
- 트랙 사용 이력 업데이트

#### 📝 라이선스
이 프로젝트는 MIT 라이선스를 따릅니다.

#### 🤝 기여하기
버그 리포트나 기능 제안은 이슈를 통해 제출해주세요.