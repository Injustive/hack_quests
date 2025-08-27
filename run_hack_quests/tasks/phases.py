import faker
from utils.client import Client
from utils.utils import (retry, check_res_status, get_utc_now,
                         get_data_lines, sleep, Logger,
                         read_json, Contract, generate_random_hex_string,
                         get_utc_now, approve_asset, asset_balance, get_decimals, approve_if_insufficient_allowance,
                         generate_random, retry_js, JSException, ModernTask, get_session, get_gas_params, estimate_gas)


class Phases:
    def __init__(self, session, client, db_manager, logger):
        self.session = session
        self.client = client
        self.db_manager = db_manager
        self.logger = logger

    @retry()
    @check_res_status()
    async def submit_quiz(self, quiz_id, index):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation SubmitQuiz($input: SubmitQuizInput!) {\n  submitQuiz(input: $input) {\n    treasure {\n      exp\n      coin\n    }\n  }\n}\n    ',
            'variables': {
                'input': {
                    'lessonId': quiz_id,
                    'status': True,
                    'quizIndex': index,
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def complete_quiz(self, quiz_id, course_id, phase_id=''):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation CompleteLesson($input: CompleteLessonInput!) {\n  completeLesson(input: $input) {\n    nextLearningInfo {\n      learningId\n      id\n      type\n      alias\n    }\n  }\n}\n    ',
            'variables': {
                'input': {
                    'lessonId': quiz_id,
                    'courseId': course_id,
                    'completeCourse': False,
                    'phaseId': phase_id,
                    'lang': 'en',
                },
            },
        }
        return await self.session.post(url, json=json_data)

    async def complete_unit(self):
        all_courses = (await self.get_all_courses()).json()['data']['ecosystem']
        current_phase = all_courses['currentPhase']['title']

        phases = []
        for phase in all_courses['phases']:
            if phase['title'] != current_phase:
                phases.append(phase)
            else:
                phases.append(phase)
                break

        all_completed = []
        for phase in all_courses['phases']:
            if phase['title'] == current_phase:
                for course in phase['courses']:
                    units = (await self.find_course_unit(course['id'])).json()['data']['findCourseDetail']['units']
                    for unit in units:
                        pages = unit['pages']
                        if all(page['isCompleted'] for page in pages):
                            all_completed.append(True)
                        else:
                            all_completed.append(False)

        if all(all_completed):
            _next = False
            next_phase = None
            for phase in all_courses['phases']:
                if _next:
                    next_phase = phase
                    break
                if phase['title'] == current_phase:
                    _next = True
            await self.switch_phase(next_phase['id'])

        all_courses = (await self.get_all_courses()).json()['data']['ecosystem']
        current_phase = all_courses['currentPhase']['title']

        phase_claimed = False
        for phase in all_courses['phases']:
            if phase['title'] == current_phase:
                if phase['quizzes']:
                    for quiz in phase['quizzes']:
                        if all(quiz_item['correct'] for quiz_item in quiz['quizList']):
                            break
                        for quiz_item in quiz['quizList']:
                            await self.complete_quiz_phase(quiz['id'], quiz_item['id'])
                        self.logger.success(f"Quiz `{quiz['description']}` is completed successfully!")
                for course in phase['courses']:
                    for unit in course['units']:
                        if all(unit['isCompleted'] for unit in course['units']):
                            self.logger.info(f'Unit {unit["title"]} already completed!')
                            if not phase['rewardClaimRecord'] and not phase['certificate']:
                                if not phase_claimed:
                                    self.logger.info("Going to claim phase rewards...")
                                    claim_phase_reward_response = \
                                    (await self.claim_phase_rewards(phase['id'])).json()['data']['claimPhaseReward']
                                    self.logger.success(f"Claimed phase rewards: {claim_phase_reward_response.get('coin')}")
                                    phase_claimed = True
                            elif phase['certificate'] and not phase['certificate'].get('userCertification'):
                                await self.claim_certificate(phase['certificate']['id'])
                            continue
                    units = (await self.find_course_unit(course['id'])).json()['data']['findCourseDetail']['units']
                    for unit in units:
                        pages = unit['pages']
                        if all(page['isCompleted'] for page in pages):
                            self.logger.info(f'Unit {unit["title"]} already completed!')
                            continue
                        for page in pages:
                            if page['isCompleted']:
                                self.logger.info(f"Quiz {page['title']} already completed!")
                                continue
                            self.logger.info(f"Starting completing quiz {page['title']}...")
                            quiz_indexes = (await self.find_unique_page(page['id'])).json()['data']['findUniquePage']['content'].get("right", [])
                            right = quiz_indexes[0]['children']
                            if right:
                                for index in range(len(right)):
                                    await self.submit_quiz(page['id'], index)
                                    await sleep(3, 5)
                            else:
                                await self.submit_quiz(page['id'], 0)
                            await sleep(3, 5)
                            await self.complete_quiz(page['id'],
                                                     'd927cdac-7fcb-4516-abab-624af8e44894',
                                                     phase_id=phase['id'] if phase['id'] != "154e7446-5ed5-8136-92ce-c7023fd940bc" else '')
                        else:
                            self.logger.success(f'Unit {unit["title"]} completed successfully!')
                            return

    async def recomplete_quests(self):
        all_courses = (await self.get_all_courses()).json()['data']['ecosystem']
        current_phase = all_courses['currentPhase']['title']
        phases = []
        for phase in all_courses['phases']:
            if phase['title'] != current_phase:
                phases.append(phase)
            else:
                phases.append(phase)
                break

        for phase in phases:
            for course in phase['courses']:
                units = (await self.find_course_unit(course['id'])).json()['data']['findCourseDetail']['units']
                for unit in units:
                    pages = unit['pages']
                    if not any(page['isCompleted'] for page in pages):
                        continue
                    for page in pages:
                        quiz_indexes = (await self.find_unique_page(page['id'])).json()['data']['findUniquePage']['content'].get("right", [])
                        right = quiz_indexes[0]['children']
                        if right:
                            for index in range(len(right)):
                                await self.submit_quiz(page['id'], index)
                                await sleep(3, 5)
                        else:
                            await self.submit_quiz(page['id'], 0)
                        await sleep(3, 5)
                        await self.complete_quiz(page['id'], 'd927cdac-7fcb-4516-abab-624af8e44894')

    @retry()
    @check_res_status()
    async def find_course_unit(self, course_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    query FindCourseUnits($where: CourseV2WhereInput) {\n  findCourseDetail(where: $where) {\n    units {\n      title\n      description\n      progress\n      pages {\n        id\n        title\n        isCompleted\n      }\n    }\n    alias\n    id\n    currentPageId\n    nextPageId\n  }\n}\n    ',
            'variables': {
                'where': {
                    'id': {
                        'equals': course_id,
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def get_all_courses(self):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    query FindActiveEcosystemInfo($where: EcosystemInfoWhereUniqueInput!) {\n  ecosystem: findUniqueEcosystemInfo(where: $where) {\n    ecosystemId\n    lang\n    basic {\n      type\n      image\n    }\n    phases {\n      id\n      coin\n      title\n      progress\n      order\n      cover\n      certificateId\n      certificate {\n        id\n        image\n        name\n        template\n        chainId\n        contract\n        credits\n        extra\n        userCertification {\n          claimed\n          mint\n          username\n          certificateId\n          certificationId\n        }\n      }\n      rewardClaimRecord {\n        claimed\n        coin\n      }\n      courses {\n        id\n        alias\n        type\n        title\n        icon\n        progress\n        order\n        currentPageId\n        units {\n          id\n          currentPageId\n          title\n          progress\n          isCompleted\n        }\n      }\n      quizzes {\n        id\n        order\n        progress\n        currentPageId\n        extra\n        quizList {\n          id\n          correct\n        }\n        description\n      }\n      extra\n      build {\n        hackathons {\n          id\n          name\n          alias\n          status\n          currentStatus\n          info {\n            image\n            intro\n          }\n          timeline {\n            timeZone\n            openReviewSame\n            registrationOpen\n            registrationClose\n            submissionOpen\n            submissionClose\n            rewardTime\n          }\n        }\n      }\n    }\n    currentPhase {\n      id\n      title\n      learningInfo {\n        id\n        alias\n        type\n        learningId\n      }\n    }\n  }\n}\n    ',
            'variables': {
                'where': {
                    'ecosystemId_lang': {
                        'ecosystemId': 'b950a72f-3fdf-4581-8ddb-3a3d1630044d',
                        'lang': 'en',
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def find_unique_page(self, page_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    query FindUniquePage($where: PageV2WhereUniqueInput!) {\n  findUniquePage(where: $where) {\n    id\n    title\n    content\n    type\n    completeQuiz\n    isCompleted\n    unitPage {\n      pageId\n      unitId\n    }\n  }\n}\n    ',
            'variables': {
                'where': {
                    'id': page_id
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def claim_phase_rewards(self, phase_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation ClaimPhaseReward($phaseId: String!) {\n  claimPhaseReward(phaseId: $phaseId) {\n    coin\n    claimed\n  }\n}\n    ',
            'variables': {
                'phaseId': phase_id
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def switch_phase(self, phase_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation SwitchCurrentPhase($phaseId: String!) {\n  switchCurrentPhase(phaseId: $phaseId)\n}\n    ',
            'variables': {
                'phaseId': phase_id
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def complete_quiz_phase(self, quiz_id, task_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation SubmitPhaseQuiz($input: SubmitPhaseQuizInput!) {\n  submitPhaseQuiz(input: $input) {\n    isCompleted\n    tryAgain\n    progress\n    treasure {\n      coin\n      exp\n    }\n  }\n}\n    ',
            'variables': {
                'input': {
                    'phaseQuizId': quiz_id,
                    'lessonId': task_id,
                    'status': True,
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def claim_certificate(self, cert_id):
        url = 'https://api.hackquest.io/graphql'
        random_username = faker.Faker().user_name()
        json_data = {
            'query': '\n    mutation ClaimCertification($certificationId: String!, $username: String!) {\n  certificate: claimCertification(\n    certificationId: $certificationId\n    username: $username\n  ) {\n    id\n    claimed\n    mint\n    username\n    txId\n    userId\n    certificateId\n    certificationId\n    certificateTime\n    certification {\n      chainId\n      name\n      contract\n      extra\n    }\n  }\n}\n    ',
            'variables': {
                'certificationId': cert_id,
                'username': random_username,
            }
        }
        return await self.session.post(url, json=json_data)