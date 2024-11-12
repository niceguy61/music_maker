import os
import json
import boto3
import librosa
from mutagen.mp3 import MP3
from datetime import timedelta
import xml.etree.ElementTree as ET  # 이 줄을 추가

def get_aws_session():
    """AWS 세션 생성"""
    try:
        session = boto3.Session(profile_name='sso')
        return session
    except Exception as e:
        print(f"AWS 프로파일 로드 실패: {e}")
        raise

def create_youtube_chapters(tracks):
    """시작 시간 순서로 챕터 생성"""
    chapters = []
    
    for track in tracks:
        start_time = int(track["start_time"])
        hours = start_time // 3600
        minutes = (start_time % 3600) // 60
        seconds = start_time % 60
        
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        chapters.append(f"{time_str} {track['title']}")
    
    return "\n".join(chapters)

def get_music_info(folder_path):
    tracks = []
    
    for filename in os.listdir(folder_path):
        if filename.endswith(".mp3"):
            file_path = os.path.join(folder_path, filename)
            
            try:
                audio = MP3(file_path)
                duration = int(audio.info.length)
                
                # BPM 분석
                try:
                    y, sr = librosa.load(file_path, sr=None)
                    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                    bpm = round(float(tempo))
                except:
                    bpm = 0
                
                title = filename.replace("ES_", "").replace(".mp3", "")
                tracks.append({
                    "title": title,
                    "bpm": bpm,
                    "duration": duration,
                    "path": file_path
                })
                
                print(f"처리완료: {title} | BPM: {bpm} | 길이: {duration}초")
                
            except Exception as e:
                print(f"오류 발생 {filename}: {e}")
    
    # BPM 기준으로 정렬
    tracks_sorted_by_bpm = sorted(tracks, key=lambda x: x["bpm"])
    
    # 정렬된 트랙에 시작 시간 추가
    start_time = 0
    for track in tracks_sorted_by_bpm:
        track["start_time"] = start_time
        start_time += track["duration"]
    
    return tracks_sorted_by_bpm

def create_srt(tracks):
    srt_output = ""
    
    for i, track in enumerate(tracks, 1):
        start_time_td = timedelta(seconds=track["start_time"])
        end_time_td = timedelta(seconds=track["start_time"] + track["duration"])
        
        start_time_str = f"{str(start_time_td.seconds // 3600).zfill(2)}:" \
                        f"{str((start_time_td.seconds % 3600) // 60).zfill(2)}:" \
                        f"{str(start_time_td.seconds % 60).zfill(2)},000"
        
        end_time_str = f"{str(end_time_td.seconds // 3600).zfill(2)}:" \
                      f"{str((end_time_td.seconds % 3600) // 60).zfill(2)}:" \
                      f"{str(end_time_td.seconds % 60).zfill(2)},000"
        
        srt_output += f"{i}\n"
        srt_output += f"{start_time_str} --> {end_time_str}\n"
        srt_output += f"🎵 {track['title']} 🎵\n\n"
    
    return srt_output

def create_prompt(tracks):
    """BPM 순으로 정렬된 트랙 리스트로 프롬프트 생성"""
    total_duration = sum(track['duration'] for track in tracks)
    tracks_list = "\n".join([
        f"- {track['title']} (BPM: {track['bpm']}, 길이: {str(timedelta(seconds=track['duration']))})"
        for track in tracks
    ])
    
    prompt = f"""
로파이 재즈 플레이리스트의 유튜브 콘텐츠를 생성해주세요.

플레이리스트 정보:
총 재생시간: {str(timedelta(seconds=total_duration))}
수록곡 (BPM 순):
{tracks_list}

다음 형식으로 한글로 응답해주세요:
1. 유튜브 제목: (감성적이고 매력적인 제목)
2. 유튜브 설명: (플레이리스트 특징과 분위기를 설명)
3. 해시태그: (로파이, 재즈 관련 해시태그 15개)
"""
    return prompt

def generate_content(prompt, session):
    bedrock = session.client('bedrock-runtime', region_name='ap-northeast-2')
    
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })
        
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        return response_body['content'][0]['text']
        
    except Exception as e:
        print(f"Bedrock API 호출 실패: {e}")
        print(f"상세 에러: {str(e)}")
        return None

def save_content(content, chapters, output_file='youtube_content.txt'):
    """Bedrock 응답과 챕터 정보를 함께 저장"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
            f.write("\n\n타임스탬프:\n")
            f.write(chapters)
        print(f"콘텐츠가 {output_file}로 저장되었습니다.")
    except Exception as e:
        print(f"파일 저장 실패: {e}")

def create_premiere_xml(tracks):
    """Final Cut Pro XML 형식으로 생성"""
    try:
        root = ET.Element('xmeml', {'version': '4'})
        
        # 프로젝트 설정
        project = ET.SubElement(root, 'sequence')
        ET.SubElement(project, 'name').text = 'Lofi Jazz Playlist'
        ET.SubElement(project, 'duration').text = '1800'
        
        # 시퀀스 설정
        rate = ET.SubElement(project, 'rate')
        ET.SubElement(rate, 'timebase').text = '30'
        ET.SubElement(rate, 'ntsc').text = 'TRUE'
        
        # 타임코드 설정
        timecode = ET.SubElement(project, 'timecode')
        tc_rate = ET.SubElement(timecode, 'rate')
        ET.SubElement(tc_rate, 'timebase').text = '30'
        ET.SubElement(tc_rate, 'ntsc').text = 'TRUE'
        ET.SubElement(timecode, 'string').text = '00:00:00:00'
        ET.SubElement(timecode, 'frame').text = '0'
        ET.SubElement(timecode, 'displayformat').text = 'NDF'
        
        # 미디어 트랙
        media = ET.SubElement(project, 'media')
        audio = ET.SubElement(media, 'audio')
        
        # 오디오 트랙 설정
        track = ET.SubElement(audio, 'track')
        ET.SubElement(track, 'enabled').text = 'TRUE'
        ET.SubElement(track, 'locked').text = 'FALSE'
        
        # 각 음악 클립 추가
        for track_info in tracks:
            clipitem = ET.SubElement(track, 'clipitem')
            ET.SubElement(clipitem, 'name').text = track_info['title']
            ET.SubElement(clipitem, 'enabled').text = 'TRUE'
            ET.SubElement(clipitem, 'duration').text = str(int(track_info['duration'] * 30))
            
            # 시작 및 종료 시간
            ET.SubElement(clipitem, 'in').text = '0'
            ET.SubElement(clipitem, 'out').text = str(int(track_info['duration'] * 30))
            ET.SubElement(clipitem, 'start').text = str(int(track_info['start_time'] * 30))
            ET.SubElement(clipitem, 'end').text = str(int((track_info['start_time'] + track_info['duration']) * 30))
            
            # 파일 정보
            file = ET.SubElement(clipitem, 'file')
            ET.SubElement(file, 'name').text = os.path.basename(track_info['path'])
            ET.SubElement(file, 'pathurl').text = f"file://localhost/{track_info['path'].replace(os.sep, '/')}"
            
            # 미디어 설정
            media = ET.SubElement(file, 'media')
            
            # 오디오 설정
            audio = ET.SubElement(media, 'audio')
            audio_track = ET.SubElement(audio, 'track')
            ET.SubElement(audio_track, 'samplecharacteristics')
            samplerate = ET.SubElement(audio_track, 'samplerate')
            ET.SubElement(samplerate, 'timebase').text = '48000'
            ET.SubElement(audio_track, 'channelcount').text = '2'
        
        # XML 파일 생성 및 저장
        xml_path = 'premiere_sequence.xml'
        
        # XML 파일 저장 (들여쓰기 포함)
        from xml.dom import minidom
        xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_str)
            
        print(f"XML 파일이 성공적으로 생성되었습니다: {xml_path}")
        return xml_path
        
    except Exception as e:
        print(f"XML 생성 중 오류 발생: {str(e)}")
        return None

def main():
    # AWS 프로파일 설정
    try:
        session = get_aws_session()
    except Exception as e:
        print(f"AWS 세션 생성 실패: {e}")
        return

    # 폴더 경로 설정
    folder_path = '../audio_lofi_jazz/reference/12th'
    
    # 음악 정보 수집
    tracks = get_music_info(folder_path)

    # 유튜브 챕터 생성
    chapters = create_youtube_chapters(tracks)
    
    # SRT 파일 생성
    srt_content = create_srt(tracks)
    with open('output.srt', 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    # Bedrock 프롬프트에 챕터 정보 추가
    prompt = create_prompt(tracks)
    
    # Bedrock으로 콘텐츠 생성
    content = generate_content(prompt, session)

    # Premiere Pro XML 생성
    xml_path = create_premiere_xml(tracks)
    print(f"Premiere Pro 시퀀스 XML이 {xml_path}로 저장되었습니다.")
    
    # 결과 저장 (Bedrock 응답 + 챕터)
    if content:
        save_content(content, chapters)

if __name__ == "__main__":
    main()