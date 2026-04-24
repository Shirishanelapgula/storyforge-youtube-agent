from dotenv import load_dotenv
load_dotenv()
from agents.story_agent import StoryAgent

agent = StoryAgent()
story = agent.generate_story('shorts', 'kindness to strangers', 'telugu')
print('Story:', story['title'])
print()
for s in story['scenes']:
    vd = s.get('visual_description', 'MISSING')
    narr = s.get('narration', '')[:50]
    num = s.get('scene_number', '?')
    print(f'Scene {num}:')
    print(f'  Narration: {narr}...')
    print(f'  Visual:    {vd[:100]}')
    print()
