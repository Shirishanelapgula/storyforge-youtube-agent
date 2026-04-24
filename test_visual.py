from dotenv import load_dotenv
load_dotenv()
from agents.story_agent import StoryAgent

agent = StoryAgent()
story = agent.generate_story('shorts', 'kindness to strangers', 'telugu')
print('Story:', story['title'])
print()
all_english = True
for s in story['scenes']:
    vd = s.get('visual_description', 'MISSING')
    ascii_ratio = sum(1 for c in vd if c.isascii()) / max(len(vd), 1)
    status = 'ENGLISH' if ascii_ratio > 0.6 else 'TELUGU/WRONG'
    if status != 'ENGLISH':
        all_english = False
    print(f'Scene {s.get(chr(115)+chr(99)+chr(101)+chr(110)+chr(101)+chr(95)+chr(110)+chr(117)+chr(109)+chr(98)+chr(101)+chr(114), 0)}:')
    print(f'  Status: {status}')
    print(f'  Visual: {vd[:100]}')
    print()
print('All English:', all_english)
